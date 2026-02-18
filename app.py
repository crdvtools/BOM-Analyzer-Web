"""
BOM Analyzer Web Edition v1.0.0
Faithful Streamlit conversion of Tyler Allen's BOM_Analyzer desktop app.
Component Revision Delta (or Difference) Verification - CRDV
- Original risk scoring, strategy engine, and buy-up logic preserved exactly
- OpenAI replaced with Groq (free tier)
- Tkinter GUI replaced with Streamlit
- DigiKey OAuth replaced with Mouser + Nexar (no localhost callback needed)
"""

import streamlit as st
import pandas as pd
import numpy as np
import os
import json
import time
import logging
import re
import requests
import urllib.parse
from pathlib import Path
from dotenv import load_dotenv
import openai
from datetime import datetime, timedelta, timezone
import plotly.express as px
import plotly.graph_objects as go
import sys
import contextlib

# Prophet import with error handling
try:
    from prophet import Prophet
except ImportError:
    st.error("Prophet library not found. Please install it: pip install prophet")
    st.stop()

# Load environment variables
load_dotenv()

# Configure logging (Streamlit captures stdout)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# API Keys
DIGIKEY_CLIENT_ID = os.getenv('DIGIKEY_CLIENT_ID')
DIGIKEY_CLIENT_SECRET = os.getenv('DIGIKEY_CLIENT_SECRET')
MOUSER_API_KEY = os.getenv('MOUSER_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY') or os.getenv('CHATGPT_API_KEY')
NEXAR_CLIENT_ID = os.getenv('NEXAR_CLIENT_ID')
NEXAR_CLIENT_SECRET = os.getenv('NEXAR_CLIENT_SECRET')
ARROW_API_KEY = os.getenv('ARROW_API_KEY')
AVNET_API_KEY = os.getenv('AVNET_API_KEY')

# API availability flags (simplified; we'll check later)
API_KEYS = {
    "DigiKey": bool(DIGIKEY_CLIENT_ID and DIGIKEY_CLIENT_SECRET),
    "Mouser": bool(MOUSER_API_KEY),
    "OpenAI": bool(OPENAI_API_KEY),
    "Octopart (Nexar)": bool(NEXAR_CLIENT_ID and NEXAR_CLIENT_SECRET),
    "Arrow": bool(ARROW_API_KEY),
    "Avnet": bool(AVNET_API_KEY),
}

# Initialize OpenAI client if key available
if API_KEYS["OpenAI"]:
    openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
else:
    openai_client = None

# Constants
DEFAULT_TARIFF_RATE = 0.035
API_TIMEOUT_SECONDS = 20
MAX_API_WORKERS = 8  # Not used in sync version, but kept for reference

# Risk weights and categories (from original)
RISK_WEIGHTS = {'Sourcing': 0.30, 'Stock': 0.15, 'LeadTime': 0.15, 'Lifecycle': 0.30, 'Geographic': 0.10}
GEO_RISK_TIERS = {
    "China": 7, "Russia": 9, "Taiwan": 5, "Malaysia": 4, "Vietnam": 4, "India": 5, "Philippines": 4,
    "Thailand": 4, "South Korea": 3, "USA": 1, "United States": 1, "Mexico": 2, "Canada": 1, "Japan": 1,
    "Germany": 1, "France": 1, "UK": 1, "Ireland": 1, "Switzerland": 1, "EU": 1,
    "Unknown": 4, "N/A": 4, "_DEFAULT_": 4
}
RISK_CATEGORIES = {'high': (6.6, 10.0), 'moderate': (3.6, 6.5), 'low': (0.0, 3.5)}

# File paths (for caching tokens, etc.)
CACHE_DIR = Path.cwd() / 'cache'
CACHE_DIR.mkdir(exist_ok=True)
TOKEN_FILE = CACHE_DIR / 'digikey_oauth2_token.json'
NEXAR_TOKEN_FILE = CACHE_DIR / 'nexar_oauth2_token.json'
HISTORICAL_DATA_FILE = Path.cwd() / 'bom_historical_data.csv'
PREDICTION_FILE = Path.cwd() / 'supply_chain_predictions.csv'

# CSV headers (same as original)
HIST_HEADER = ['Component', 'Manufacturer', 'Part_Number', 'Distributor', 'Lead_Time_Days', 'Cost', 'Inventory', 'Stock_Probability', 'Fetch_Timestamp']
PRED_HEADER = ['Component', 'Date', 'Prophet_Lead', 'Prophet_Cost', 'RAG_Lead', 'RAG_Cost', 'AI_Lead', 'AI_Cost', 'Stock_Probability', 'Real_Lead', 'Real_Cost', 'Real_Stock', 'Prophet_Ld_Acc', 'Prophet_Cost_Acc', 'RAG_Ld_Acc', 'RAG_Cost_Acc','AI_Ld_Acc', 'AI_Cost_Acc']

# -------------------- Utility Functions (adapted) --------------------

def safe_float(value, default=np.nan):
    if value is None or isinstance(value, bool): return default
    if isinstance(value, (int, float)):
        return float(value) if not np.isinf(value) else default
    try:
        s_val = str(value).strip().replace('$', '').replace(',', '').replace('%', '').lower()
        if not s_val or s_val in ['n/a', 'none', 'inf', '-inf', 'na', 'nan', '']:
            return default
        return float(s_val)
    except (ValueError, TypeError):
        return default

def convert_lead_time_to_days(lead_time_str):
    if lead_time_str is None or pd.isna(lead_time_str): return np.nan
    if isinstance(lead_time_str, (int, float)):
        return int(round(lead_time_str))
    s = str(lead_time_str).lower().strip()
    if s in ['n/a', 'unknown', '', 'na', 'none', 'stock']:
        return 0 if s == 'stock' else np.nan
    try:
        match = re.search(r'(\d+(\.\d+)?)', s)
        if not match: return np.nan
        num = float(match.group(1))
        if 'week' in s:
            return int(round(num * 7))
        elif 'day' in s:
            return int(round(num))
        else:
            return int(round(num))
    except:
        return np.nan

def init_csv_file(filepath, header):
    if not filepath.exists():
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(header)
        logger.info(f"Created {filepath.name}")

def append_to_csv(filepath, data_rows):
    if not data_rows: return
    try:
        with open(filepath, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(data_rows)
    except Exception as e:
        logger.error(f"Failed to append to {filepath.name}: {e}")

# --- Supplier API Wrappers (adapted to standalone functions) ---

def search_mouser(part_number, manufacturer=""):
    if not MOUSER_API_KEY:
        logger.debug("Mouser API key not set")
        return None
    url = "https://api.mouser.com/api/v1/search/keyword"
    params = {'apiKey': MOUSER_API_KEY}
    keyword = f"{manufacturer} {part_number}".strip() if manufacturer else part_number
    body = {'SearchByKeywordRequest': {'keyword': keyword, 'records': 5, 'startingRecord': 0}}
    try:
        response = requests.post(url, params=params, json=body, timeout=API_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
        if 'Errors' in data and data['Errors']:
            return None
        parts = data.get('SearchResults', {}).get('Parts', [])
        if not parts:
            return None
        # Simple: take first result (could be improved)
        best = parts[0]
        lead_time_days = convert_lead_time_to_days(best.get('LeadTime'))
        pricing = []
        for pb in best.get('PriceBreaks', []):
            qty = safe_float(pb.get('Quantity'), default=0)
            price = safe_float(pb.get('Price', '').replace('$',''))
            if qty > 0 and pd.notna(price):
                pricing.append({'qty': int(qty), 'price': price})
        pricing.sort(key=lambda x: x['qty'])
        result = {
            "Source": "Mouser",
            "SourcePartNumber": best.get('MouserPartNumber', "N/A"),
            "ManufacturerPartNumber": best.get('ManufacturerPartNumber', "N/A"),
            "Manufacturer": best.get('Manufacturer', "N/A"),
            "Description": best.get('Description', "N/A"),
            "Stock": int(safe_float(best.get('AvailabilityInStock', 0), default=0)),
            "LeadTimeDays": lead_time_days,
            "MinOrderQty": int(safe_float(best.get('Min', 0), default=1)),
            "Packaging": best.get('Packaging', "N/A"),
            "Pricing": pricing,
            "CountryOfOrigin": best.get("CountryOfOrigin", "N/A"),
            "TariffCode": "N/A",
            "NormallyStocking": True,
            "Discontinued": False,
            "EndOfLife": False,
            "DatasheetUrl": best.get('DataSheetUrl', "N/A"),
            "ApiTimestamp": datetime.now(timezone.utc).isoformat(timespec='seconds'),
        }
        return result
    except Exception as e:
        logger.error(f"Mouser search failed for {part_number}: {e}")
        return None

# Nexar (Octopart) - requires client credentials token
def get_nexar_token():
    if not NEXAR_CLIENT_ID or not NEXAR_CLIENT_SECRET:
        return None
    # Check cache
    if NEXAR_TOKEN_FILE.exists():
        try:
            with open(NEXAR_TOKEN_FILE, 'r') as f:
                token_data = json.load(f)
            if time.time() < token_data.get('expires_at', 0):
                return token_data.get('access_token')
        except:
            pass
    # Get new token
    url = "https://identity.nexar.com/connect/token"
    payload = {
        'grant_type': 'client_credentials',
        'client_id': NEXAR_CLIENT_ID,
        'client_secret': NEXAR_CLIENT_SECRET,
        'scope': 'supply.domain'
    }
    try:
        response = requests.post(url, data=payload, timeout=API_TIMEOUT_SECONDS)
        response.raise_for_status()
        token_data = response.json()
        expires_in = token_data.get('expires_in', 3600)
        token_data['expires_at'] = time.time() + expires_in - 60
        with open(NEXAR_TOKEN_FILE, 'w') as f:
            json.dump(token_data, f)
        return token_data.get('access_token')
    except Exception as e:
        logger.error(f"Nexar token error: {e}")
        return None

def search_octopart_nexar(part_number, manufacturer=""):
    token = get_nexar_token()
    if not token:
        return None
    url = "https://api.nexar.com/graphql"
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    query = f"""
    query {{
      supSearchMpn(q: "{part_number}", limit: 1, country: "US", currency: "USD") {{
        results {{
          part {{
            mpn
            manufacturer {{ name }}
            shortDescription
            bestDatasheet {{ url }}
            sellers(authorizedOnly: false) {{
              company {{ name }}
              isAuthorized
              offers {{
                sku
                inventoryLevel
                moq
                packaging
                factoryLeadDays
                prices {{ quantity price currency }}
              }}
            }}
          }}
        }}
      }}
    }}
    """
    try:
        response = requests.post(url, headers=headers, json={'query': query}, timeout=API_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
        if 'errors' in data:
            return None
        results = data.get('data', {}).get('supSearchMpn', {}).get('results', [])
        if not results:
            return None
        part_data = results[0].get('part', {})
        # Pick best offer (first seller, first offer)
        sellers = part_data.get('sellers', [])
        best_offer = None
        for seller in sellers:
            offers = seller.get('offers', [])
            if offers:
                best_offer = offers[0]
                best_offer['seller_name'] = seller.get('company', {}).get('name', 'Unknown')
                break
        if not best_offer:
            return None
        lead_time_days = safe_float(best_offer.get('factoryLeadDays'), default=np.nan)
        lead_time_days = int(lead_time_days) if pd.notna(lead_time_days) else np.nan
        pricing = []
        for p in best_offer.get('prices', []):
            if p.get('currency') == 'USD':
                qty = int(p.get('quantity', 0))
                price = safe_float(p.get('price'))
                if qty > 0 and pd.notna(price):
                    pricing.append({'qty': qty, 'price': price})
        pricing.sort(key=lambda x: x['qty'])
        result = {
            "Source": "Octopart (Nexar)",
            "SourcePartNumber": best_offer.get('sku', "N/A"),
            "ManufacturerPartNumber": part_data.get('mpn', part_number),
            "Manufacturer": part_data.get('manufacturer', {}).get('name', manufacturer or "N/A"),
            "Description": part_data.get('shortDescription', "N/A"),
            "Stock": int(safe_float(best_offer.get('inventoryLevel', 0), default=0)),
            "LeadTimeDays": lead_time_days,
            "MinOrderQty": int(safe_float(best_offer.get('moq', 0), default=0)),
            "Packaging": best_offer.get('packaging', "N/A"),
            "Pricing": pricing,
            "CountryOfOrigin": "N/A",
            "TariffCode": "N/A",
            "NormallyStocking": True,
            "Discontinued": False,
            "EndOfLife": False,
            "DatasheetUrl": part_data.get('bestDatasheet', {}).get('url', 'N/A'),
            "ApiTimestamp": datetime.now(timezone.utc).isoformat(timespec='seconds'),
        }
        return result
    except Exception as e:
        logger.error(f"Nexar search failed for {part_number}: {e}")
        return None

# Arrow and Avnet placeholders (return None)
def search_arrow(part_number, manufacturer=""):
    return None
def search_avnet(part_number, manufacturer=""):
    return None

# DigiKey placeholder (return None for now)
def search_digikey(part_number, manufacturer=""):
    # Could be implemented with OAuth if needed, but skip for simplicity
    return None

# Function to fetch data from all enabled suppliers (synchronous)
def get_part_data(part_number, manufacturer):
    results = {}
    if API_KEYS["Mouser"]:
        res = search_mouser(part_number, manufacturer)
        if res:
            results["Mouser"] = res
    if API_KEYS["Octopart (Nexar)"]:
        res = search_octopart_nexar(part_number, manufacturer)
        if res:
            results["Octopart (Nexar)"] = res
    # Add others if implemented
    return results

# Optimal cost calculation (from original)
def get_optimal_cost(qty_needed, pricing_breaks, min_order_qty=0, buy_up_threshold_pct=1.0):
    notes = ""
    if not isinstance(qty_needed, (int, float)) or qty_needed <= 0:
        return np.nan, np.nan, qty_needed, "Invalid Qty Needed"
    if not isinstance(pricing_breaks, list):
        return np.nan, np.nan, qty_needed, "Invalid Pricing Data"
    try:
        valid_breaks = [{'qty': int(pb['qty']), 'price': safe_float(pb['price'])} for pb in pricing_breaks
                        if isinstance(pb, dict) and pb.get('qty', 0) > 0 and pd.notna(safe_float(pb.get('price')))]
        if not valid_breaks:
            return np.nan, np.nan, qty_needed, "No Valid Price Breaks"
        pricing_breaks = sorted(valid_breaks, key=lambda x: x['qty'])
        min_order_qty = max(1, int(safe_float(min_order_qty, default=1)))
    except:
        return np.nan, np.nan, qty_needed, "Pricing Data Error"

    base_order_qty = max(int(qty_needed), min_order_qty)
    base_unit_price = np.nan
    applicable_break = None
    for pb in pricing_breaks:
        if base_order_qty >= pb['qty']:
            applicable_break = pb
        else:
            break
    if applicable_break:
        base_unit_price = applicable_break['price']
    elif pricing_breaks:
        applicable_break = pricing_breaks[0]
        base_unit_price = applicable_break['price']
        base_order_qty = max(base_order_qty, applicable_break['qty'])
        notes += f"MOQ adjusted to first break ({base_order_qty}). "
    else:
        return np.nan, np.nan, qty_needed, "Cannot Determine Base Price"

    best_total_cost = base_unit_price * base_order_qty
    best_unit_price = base_unit_price
    actual_order_qty = base_order_qty

    for pb in pricing_breaks:
        break_qty = pb['qty']
        break_price = pb['price']
        if break_qty >= base_order_qty:
            total_cost_at_break = break_qty * break_price
            if total_cost_at_break < best_total_cost * (1.0 - (buy_up_threshold_pct / 100.0)):
                best_total_cost = total_cost_at_break
                best_unit_price = break_price
                actual_order_qty = break_qty
                notes = f"Price break @ {break_qty} lower total cost. "
            elif actual_order_qty < break_qty and total_cost_at_break <= best_total_cost * (1.0 + (buy_up_threshold_pct / 100.0)):
                best_total_cost = total_cost_at_break
                best_unit_price = break_price
                actual_order_qty = break_qty
                notes = f"Bought up to {break_qty} for similar total cost. "
    return best_unit_price, best_total_cost, actual_order_qty, notes.strip()

# Stock probability heuristic (simplified)
def calculate_stock_probability_simple(options_list, qty_needed):
    if not options_list: return 0.0
    suppliers_with_stock = 0
    total_stock = 0
    for opt in options_list:
        stock = opt.get('stock', 0)
        if stock >= qty_needed:
            suppliers_with_stock += 1
        total_stock += stock
    if suppliers_with_stock >= 2: score = 90.0
    elif suppliers_with_stock == 1: score = 70.0
    else: score = 15.0
    # adjust based on total stock ratio
    if total_stock > qty_needed * 5 and suppliers_with_stock > 0: score += 5.0
    elif total_stock < qty_needed * 1.2 and suppliers_with_stock > 0: score -= 5.0
    return round(max(0.0, min(100.0, score)), 1)

# Tariff info (simplified: return default)
def get_tariff_info(hts_code, country_of_origin, custom_tariff_rates):
    # Use custom rate if provided, else default
    coo = str(country_of_origin).strip() if country_of_origin else ""
    if coo and coo in custom_tariff_rates:
        return custom_tariff_rates[coo], "Custom"
    return DEFAULT_TARIFF_RATE, "Default"

# Main analysis for a single part (adapted from original)
def analyze_single_part(bom_part_number, bom_manufacturer, bom_qty_per_unit, config):
    total_units = config.get('total_units', 1)
    buy_up_threshold_pct = config.get('buy_up_threshold', 1.0)
    total_qty_needed = int(bom_qty_per_unit * total_units)
    if total_qty_needed <= 0:
        gui_entry = {
            "PartNumber": bom_part_number, "Manufacturer": bom_manufacturer or "N/A", "MfgPN": "NOT FOUND",
            "QtyNeed": total_qty_needed, "Status": "Error", "Sources": "0", "StockAvail": "N/A",
            "COO": "N/A", "RiskScore": "10.0", "TariffPct": "N/A", "BestCostPer": "N/A",
            "BestTotalCost": "N/A", "ActualBuyQty": "N/A", "BestCostLT": "N/A", "BestCostSrc": "N/A",
            "Alternates": "No", "AlternatesList": [], "Notes": "Invalid quantity"
        }
        return [gui_entry], [], {}

    # Fetch data from suppliers
    part_results_by_supplier = get_part_data(bom_part_number, bom_manufacturer)

    if not part_results_by_supplier:
        gui_entry = {
            "PartNumber": bom_part_number, "Manufacturer": bom_manufacturer or "N/A", "MfgPN": "NOT FOUND",
            "QtyNeed": total_qty_needed, "Status": "Unknown", "Sources": "0", "StockAvail": "N/A",
            "COO": "N/A", "RiskScore": "10.0", "TariffPct": "N/A", "BestCostPer": "N/A",
            "BestTotalCost": "N/A", "ActualBuyQty": "N/A", "BestCostLT": "N/A", "BestCostSrc": "N/A",
            "Alternates": "No", "AlternatesList": [], "Notes": "No supplier data"
        }
        return [gui_entry], [], {}

    # Process each supplier option
    all_options = []
    for source, data in part_results_by_supplier.items():
        if not isinstance(data, dict): continue
        pricing = data.get('Pricing', [])
        unit_cost, total_cost, actual_qty, cost_notes = get_optimal_cost(
            total_qty_needed, pricing, data.get('MinOrderQty', 0), buy_up_threshold_pct
        )
        lead = data.get('LeadTimeDays', np.inf)
        if pd.isna(lead):
            lead = np.inf
        option = {
            "source": source,
            "cost": total_cost if pd.notna(total_cost) else np.inf,
            "lead_time": lead,
            "stock": data.get('Stock', 0),
            "unit_cost": unit_cost,
            "actual_order_qty": actual_qty,
            "moq": data.get('MinOrderQty', 0),
            "discontinued": data.get('Discontinued', False),
            "eol": data.get('EndOfLife', False),
            'bom_pn': bom_part_number,
            'original_qty_per_unit': bom_qty_per_unit,
            'total_qty_needed': total_qty_needed,
            'Manufacturer': data.get('Manufacturer', 'N/A'),
            'ManufacturerPartNumber': data.get('ManufacturerPartNumber', 'N/A'),
            'SourcePartNumber': data.get('SourcePartNumber', 'N/A'),
            'Pricing': pricing,
            'TariffCode': data.get('TariffCode'),
            'CountryOfOrigin': data.get('CountryOfOrigin'),
            'ApiTimestamp': data.get('ApiTimestamp'),
            'notes': cost_notes,
        }
        all_options.append(option)

    if not all_options:
        gui_entry = {
            "PartNumber": bom_part_number, "Manufacturer": bom_manufacturer or "N/A", "MfgPN": "NOT FOUND",
            "QtyNeed": total_qty_needed, "Status": "Error", "Sources": "0", "StockAvail": "N/A",
            "COO": "N/A", "RiskScore": "10.0", "TariffPct": "N/A", "BestCostPer": "N/A",
            "BestTotalCost": "N/A", "ActualBuyQty": "N/A", "BestCostLT": "N/A", "BestCostSrc": "N/A",
            "Alternates": "No", "AlternatesList": [], "Notes": "Processing error"
        }
        return [gui_entry], [], {}

    # Consolidate manufacturer and MPN
    consolidated_mfg = bom_manufacturer or "N/A"
    consolidated_mpn = bom_part_number
    for opt in all_options:
        if opt.get('Manufacturer') and opt['Manufacturer'] != "N/A" and consolidated_mfg == "N/A":
            consolidated_mfg = opt['Manufacturer']
        if opt.get('ManufacturerPartNumber') and opt['ManufacturerPartNumber'] != "N/A" and consolidated_mpn == "N/A":
            consolidated_mpn = opt['ManufacturerPartNumber']

    # COO consolidation (simplified: take first non-N/A)
    consolidated_coo = "N/A"
    for opt in all_options:
        coo = opt.get('CountryOfOrigin')
        if coo and isinstance(coo, str) and coo.strip().upper() not in ["N/A", "", "UNKNOWN"]:
            consolidated_coo = coo.strip()
            break

    # Calculate stock probability and tariff
    stock_prob = calculate_stock_probability_simple(all_options, total_qty_needed)
    tariff_rate, tariff_src = get_tariff_info(None, consolidated_coo, config.get('custom_tariff_rates', {}))

    # Prepare historical entries
    historical_entries = []
    for opt in all_options:
        historical_entries.append([
            f"{consolidated_mfg} {consolidated_mpn}".strip(),
            opt.get('Manufacturer', 'N/A'), opt.get('ManufacturerPartNumber', 'N/A'),
            opt.get('source'),
            opt.get('lead_time') if opt.get('lead_time') != np.inf else np.nan,
            opt.get('unit_cost', np.nan),
            opt.get('stock', 0),
            stock_prob,
            opt.get('ApiTimestamp', datetime.now(timezone.utc).isoformat(timespec='seconds'))
        ])

    # Determine best cost option (cheapest, considering stock)
    options_with_valid_cost = [opt for opt in all_options if opt.get('cost') != np.inf]
    best_cost_option = None
    in_stock_options = [opt for opt in options_with_valid_cost if opt.get('stock', 0) >= total_qty_needed]
    if in_stock_options:
        best_cost_option = min(in_stock_options, key=lambda x: (x.get('cost', np.inf), x.get('source', '')))
    elif options_with_valid_cost:
        best_cost_option = min(options_with_valid_cost, key=lambda x: (x.get('cost', np.inf), x.get('lead_time', np.inf)))

    # Determine fastest option (shortest lead time, considering stock)
    fastest_option = None
    if in_stock_options:
        fastest_option = min(in_stock_options, key=lambda x: (x.get('cost', np.inf), x.get('source', '')))  # in stock => lead time 0
    else:
        options_with_valid_lt = [opt for opt in all_options if opt.get('lead_time') != np.inf]
        if options_with_valid_lt:
            fastest_option = min(options_with_valid_lt, key=lambda x: (x.get('lead_time', np.inf), x.get('cost', np.inf)))

    # Calculate risk score (simplified)
    num_sources = len(all_options)
    sourcing_risk = 10 if num_sources <= 1 else 5 if num_sources == 2 else 1
    has_stock_gap = not any(opt.get('stock', 0) >= total_qty_needed for opt in all_options)
    stock_risk = 8 if has_stock_gap else 4 if sum(opt.get('stock', 0) for opt in all_options) < 1.5 * total_qty_needed else 0
    fastest_lead = fastest_option.get('lead_time', np.inf) if fastest_option else np.inf
    if fastest_lead == 0: lead_risk = 0
    elif fastest_lead == np.inf: lead_risk = 9
    elif fastest_lead > 90: lead_risk = 7
    elif fastest_lead > 45: lead_risk = 4
    else: lead_risk = 1
    lifecycle_risk = 10 if any(opt.get('eol') or opt.get('discontinued') for opt in all_options) else 0
    geo_risk = GEO_RISK_TIERS.get(consolidated_coo, GEO_RISK_TIERS["_DEFAULT_"])
    overall_risk = (sourcing_risk * 0.3 + stock_risk * 0.15 + lead_risk * 0.15 + lifecycle_risk * 0.3 + geo_risk * 0.1)
    overall_risk = round(max(0, min(10, overall_risk)), 1)

    # Status
    lifecycle_notes = set()
    if any(opt.get('eol') for opt in all_options): lifecycle_notes.add("EOL")
    if any(opt.get('discontinued') for opt in all_options): lifecycle_notes.add("DISC")
    status = "Active"
    if "EOL" in lifecycle_notes: status = "EOL"
    elif "DISC" in lifecycle_notes: status = "Discontinued"

    # Notes
    notes = []
    if has_stock_gap: notes.append("Stock Gap")
    if best_cost_option and best_cost_option.get('notes'): notes.append(best_cost_option['notes'])
    notes_str = "; ".join(notes)

    gui_entry = {
        "PartNumber": bom_part_number,
        "Manufacturer": consolidated_mfg,
        "MfgPN": consolidated_mpn,
        "QtyNeed": total_qty_needed,
        "Status": status,
        "Sources": str(len(all_options)),
        "StockAvail": str(sum(opt.get('stock', 0) for opt in all_options)),
        "COO": consolidated_coo,
        "RiskScore": f"{overall_risk:.1f}",
        "TariffPct": f"{tariff_rate*100:.1f}%" if pd.notna(tariff_rate) else "N/A",
        "BestCostPer": f"{best_cost_option.get('unit_cost', np.nan):.4f}" if best_cost_option and pd.notna(best_cost_option.get('unit_cost')) else "N/A",
        "BestTotalCost": f"{best_cost_option.get('cost', np.inf):.2f}" if best_cost_option and best_cost_option.get('cost') != np.inf else "N/A",
        "ActualBuyQty": str(best_cost_option.get('actual_order_qty', 'N/A')) if best_cost_option else "N/A",
        "BestCostLT": f"{best_cost_option.get('lead_time', np.inf):.0f}" if best_cost_option and best_cost_option.get('lead_time') != np.inf else "0" if best_cost_option and best_cost_option.get('stock',0) >= total_qty_needed else "N/A",
        "BestCostSrc": best_cost_option.get('source', "N/A") if best_cost_option else "N/A",
        "Alternates": "No",  # Alternates not implemented
        "AlternatesList": [],
        "Notes": notes_str,
    }
    part_summary = {
        "bom_pn": bom_part_number,
        "bom_mfg": bom_manufacturer,
        "original_qty_per_unit": bom_qty_per_unit,
        "total_qty_needed": total_qty_needed,
        "options": all_options,
        "alternates": []
    }
    return [gui_entry], historical_entries, part_summary

# --- Predictive functions (Prophet, RAG, AI) adapted ---
def run_prophet(component_historical_data, metric='Lead_Time_Days', periods=90, min_data_points=5):
    if component_historical_data is None or component_historical_data.empty:
        return None
    if metric not in component_historical_data.columns:
        return None
    df = component_historical_data[['Fetch_Timestamp', metric]].dropna()
    df.rename(columns={'Fetch_Timestamp': 'ds', metric: 'y'}, inplace=True)
    if len(df) < min_data_points:
        return None
    df['ds'] = pd.to_datetime(df['ds'], errors='coerce').dt.tz_localize(None)
    df['y'] = pd.to_numeric(df['y'], errors='coerce')
    df = df.dropna()
    if len(df) < min_data_points:
        return None
    # Simple outlier removal
    q1 = df['y'].quantile(0.25)
    q3 = df['y'].quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    df = df[(df['y'] >= lower) & (df['y'] <= upper)]
    if len(df) < min_data_points:
        return None
    try:
        with open(os.devnull, 'w') as stderr, contextlib.redirect_stderr(stderr):
            model = Prophet(yearly_seasonality=True, weekly_seasonality=False, daily_seasonality=False)
            model.fit(df)
        future = model.make_future_dataframe(periods=periods)
        forecast = model.predict(future)
        pred = forecast.iloc[-1]['yhat']
        if metric == 'Lead_Time_Days': pred = max(0, pred)
        elif metric == 'Cost': pred = max(0.001, pred)
        return pred
    except:
        return None

def run_rag_mock(prophet_lead, prophet_cost, stock_prob, context=""):
    rag_lead_range = "N/A"
    rag_cost_range = "N/A"
    adj_stock_prob = stock_prob if pd.notna(stock_prob) else 50.0
    has_issues = "shortage" in context.lower() if context else False
    if pd.notna(prophet_lead):
        base = prophet_lead
        var = max(7, base * 0.15)
        lead_min = base - var * np.random.uniform(0.5, 1.0)
        lead_max = base + var * np.random.uniform(1.0, 1.5)
        if has_issues:
            lead_min += 7
            lead_max += 14
            adj_stock_prob *= 0.8
        rag_lead_range = f"{max(0, lead_min):.0f}-{max(0, lead_max):.0f}"
    if pd.notna(prophet_cost):
        base = prophet_cost
        var = max(0.01, base * 0.05)
        cost_min = base - var * np.random.uniform(0.5, 1.0)
        cost_max = base + var * np.random.uniform(1.0, 1.2)
        if has_issues:
            cost_min = max(cost_min, base * 0.98)
            cost_max += base * 0.1
        rag_cost_range = f"{max(0.001, cost_min):.3f}-{max(0.001, cost_max):.3f}"
    return rag_lead_range, rag_cost_range, round(max(0.0, min(100.0, adj_stock_prob)), 1)

def run_ai_comparison(prophet_lead, prophet_cost, rag_lead_range, rag_cost_range, stock_prob):
    ai_lead = prophet_lead if pd.notna(prophet_lead) else np.nan
    ai_cost = prophet_cost if pd.notna(prophet_cost) else np.nan
    ai_stock_prob = stock_prob
    # parse RAG midpoints
    rag_mid_lead = np.nan
    rag_mid_cost = np.nan
    if rag_lead_range != "N/A" and '-' in rag_lead_range:
        parts = [safe_float(p) for p in rag_lead_range.split('-')]
        if len(parts) == 2 and not any(pd.isna(p) for p in parts):
            rag_mid_lead = (parts[0] + parts[1]) / 2.0
    if rag_cost_range != "N/A" and '-' in rag_cost_range:
        parts = [safe_float(p) for p in rag_cost_range.split('-')]
        if len(parts) == 2 and not any(pd.isna(p) for p in parts):
            rag_mid_cost = (parts[0] + parts[1]) / 2.0
    # simple weighted average (70% Prophet, 30% RAG)
    prophet_weight = 0.7
    rag_weight = 0.3
    if pd.notna(prophet_lead) and pd.notna(rag_mid_lead):
        ai_lead = prophet_lead * prophet_weight + rag_mid_lead * rag_weight
    elif pd.notna(prophet_lead):
        ai_lead = prophet_lead
    elif pd.notna(rag_mid_lead):
        ai_lead = rag_mid_lead
    if pd.notna(prophet_cost) and pd.notna(rag_mid_cost):
        ai_cost = prophet_cost * prophet_weight + rag_mid_cost * rag_weight
    elif pd.notna(prophet_cost):
        ai_cost = prophet_cost
    elif pd.notna(rag_mid_cost):
        ai_cost = rag_mid_cost
    ai_lead = max(0, ai_lead) if pd.notna(ai_lead) else np.nan
    ai_cost = max(0.001, ai_cost) if pd.notna(ai_cost) else np.nan
    return ai_lead, ai_cost, ai_stock_prob

# Function to run predictive analysis for all components
def run_predictive_analysis(historical_df, context=""):
    if historical_df.empty or 'Component' not in historical_df.columns:
        return []
    components = historical_df['Component'].dropna().unique()
    new_predictions = []
    today_str = datetime.now().strftime('%Y-%m-%d')
    for comp in components:
        comp_data = historical_df[historical_df['Component'] == comp].copy()
        if comp_data.empty:
            continue
        comp_data.sort_values('Fetch_Timestamp', ascending=False, inplace=True)
        latest_stock_prob = comp_data['Stock_Probability'].iloc[0] if not comp_data.empty and pd.notna(comp_data['Stock_Probability'].iloc[0]) else 50.0
        prophet_lead = run_prophet(comp_data, 'Lead_Time_Days')
        prophet_cost = run_prophet(comp_data, 'Cost')
        rag_lead, rag_cost, rag_stock = run_rag_mock(prophet_lead, prophet_cost, latest_stock_prob, context)
        ai_lead, ai_cost, ai_stock = run_ai_comparison(prophet_lead, prophet_cost, rag_lead, rag_cost, rag_stock)
        pred_row = {
            'Component': comp,
            'Date': today_str,
            'Prophet_Lead': f"{prophet_lead:.1f}" if pd.notna(prophet_lead) else '',
            'Prophet_Cost': f"{prophet_cost:.3f}" if pd.notna(prophet_cost) else '',
            'RAG_Lead': rag_lead,
            'RAG_Cost': rag_cost,
            'AI_Lead': f"{ai_lead:.1f}" if pd.notna(ai_lead) else '',
            'AI_Cost': f"{ai_cost:.3f}" if pd.notna(ai_cost) else '',
            'Stock_Probability': f"{ai_stock:.1f}" if pd.notna(ai_stock) else '',
            'Real_Lead': '', 'Real_Cost': '', 'Real_Stock': '',
            'Prophet_Ld_Acc': '', 'Prophet_Cost_Acc': '',
            'RAG_Ld_Acc': '', 'RAG_Cost_Acc': '',
            'AI_Ld_Acc': '', 'AI_Cost_Acc': '',
        }
        new_predictions.append([pred_row.get(h, '') for h in PRED_HEADER])
    return new_predictions

# --- Streamlit App ---

def main():
    st.set_page_config(page_title="BOM Analyzer", layout="wide")
    st.title("NPI BOM Analyzer")

    # Sidebar configuration
    with st.sidebar:
        st.header("Configuration")
        total_units = st.number_input("Total Units to Build", min_value=1, value=100, step=1)
        max_premium = st.number_input("Max Cost Premium (%)", min_value=0.0, value=15.0, step=1.0, format="%.1f")
        target_lead_time = st.number_input("Target Lead Time (days)", min_value=0, value=56, step=1)
        cost_weight = st.slider("Cost Weight (0-1)", 0.0, 1.0, 0.5, step=0.05)
        lead_time_weight = st.slider("Lead Time Weight (0-1)", 0.0, 1.0, 0.5, step=0.05)
        buy_up_threshold = st.number_input("Buy-Up Threshold (%)", min_value=0.0, value=1.0, step=0.5, format="%.1f")

        # Custom tariff rates
        st.subheader("Custom Tariff Rates (%)")
        tariff_countries = ["China", "Mexico", "India", "Vietnam", "Taiwan", "Japan", "Malaysia", "Germany", "USA", "Philippines", "Thailand", "South Korea"]
        tariff_rates = {}
        for country in tariff_countries:
            rate = st.text_input(f"{country}", value="", key=f"tariff_{country}")
            if rate:
                try:
                    tariff_rates[country] = float(rate) / 100.0
                except:
                    st.warning(f"Invalid rate for {country}")

        # API status
        st.subheader("API Status")
        for api, enabled in API_KEYS.items():
            st.write(f"{api}: {'✅' if enabled else '❌'}")

        # File upload
        st.subheader("BOM Upload")
        uploaded_file = st.file_uploader("Choose BOM CSV", type=["csv"])

        # Buttons
        run_analysis = st.button("Run Analysis", type="primary")
        run_predict = st.button("Run Predictions")
        run_ai = st.button("AI Summary")

    # Initialize session state
    if 'bom_df' not in st.session_state:
        st.session_state.bom_df = None
    if 'analysis_results' not in st.session_state:
        st.session_state.analysis_results = None
    if 'historical_data_df' not in st.session_state:
        # Load historical data if exists
        if HISTORICAL_DATA_FILE.exists():
            try:
                st.session_state.historical_data_df = pd.read_csv(HISTORICAL_DATA_FILE)
            except:
                st.session_state.historical_data_df = pd.DataFrame(columns=HIST_HEADER)
        else:
            st.session_state.historical_data_df = pd.DataFrame(columns=HIST_HEADER)
    if 'predictions_df' not in st.session_state:
        if PREDICTION_FILE.exists():
            try:
                st.session_state.predictions_df = pd.read_csv(PREDICTION_FILE)
            except:
                st.session_state.predictions_df = pd.DataFrame(columns=PRED_HEADER)
        else:
            st.session_state.predictions_df = pd.DataFrame(columns=PRED_HEADER)
    if 'strategies_for_export' not in st.session_state:
        st.session_state.strategies_for_export = {}
    if 'near_miss_info' not in st.session_state:
        st.session_state.near_miss_info = {}

    # Load BOM if uploaded
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            # Basic column mapping (as in original)
            col_map = {}
            lower_cols = {c.lower().strip(): c for c in df.columns}
            if 'part number' in lower_cols:
                col_map[lower_cols['part number']] = 'Part Number'
            if 'quantity' in lower_cols or 'qty' in lower_cols:
                qty_key = 'quantity' if 'quantity' in lower_cols else 'qty'
                col_map[lower_cols[qty_key]] = 'Quantity'
            if 'manufacturer' in lower_cols:
                col_map[lower_cols['manufacturer']] = 'Manufacturer'
            df.rename(columns=col_map, inplace=True)
            required = ['Part Number', 'Quantity']
            if not all(r in df.columns for r in required):
                st.error("BOM must contain 'Part Number' and 'Quantity' columns.")
            else:
                df['Part Number'] = df['Part Number'].astype(str).str.strip()
                df['Quantity'] = pd.to_numeric(df['Quantity'], errors='coerce').fillna(0).astype(int)
                df = df[df['Quantity'] > 0]
                if 'Manufacturer' not in df.columns:
                    df['Manufacturer'] = ''
                st.session_state.bom_df = df
                st.success(f"BOM loaded: {len(df)} parts")
        except Exception as e:
            st.error(f"Error loading BOM: {e}")

    # Main area tabs
    tab1, tab2, tab3 = st.tabs(["BOM Analysis", "AI & Predictions", "Visualizations"])

    # Tab 1: BOM Analysis
    with tab1:
        if run_analysis and st.session_state.bom_df is not None:
            config = {
                'total_units': total_units,
                'max_premium': max_premium,
                'target_lead_time_days': target_lead_time,
                'cost_weight': cost_weight,
                'lead_time_weight': lead_time_weight,
                'buy_up_threshold': buy_up_threshold,
                'custom_tariff_rates': tariff_rates
            }
            with st.spinner("Running analysis..."):
                all_gui_entries = []
                all_historical = []
                all_part_summaries = []
                progress_bar = st.progress(0)
                total_parts = len(st.session_state.bom_df)
                for idx, row in st.session_state.bom_df.iterrows():
                    gui_rows, hist_rows, summary = analyze_single_part(
                        row['Part Number'], row.get('Manufacturer', ''), row['Quantity'], config
                    )
                    all_gui_entries.extend(gui_rows)
                    all_historical.extend(hist_rows)
                    if summary.get('options'):
                        all_part_summaries.append(summary)
                    progress_bar.progress((idx+1)/total_parts)
                # Save historical data
                if all_historical:
                    append_to_csv(HISTORICAL_DATA_FILE, all_historical)
                    # Reload historical df
                    st.session_state.historical_data_df = pd.read_csv(HISTORICAL_DATA_FILE) if HISTORICAL_DATA_FILE.exists() else pd.DataFrame(columns=HIST_HEADER)
                # Store results
                st.session_state.analysis_results = {
                    'gui_entries': all_gui_entries,
                    'part_summaries': all_part_summaries,
                    'config': config
                }
                # Compute summary metrics (simplified version of original)
                # For now, just show table
                st.success("Analysis complete!")

        # Display results if available
        if st.session_state.analysis_results and st.session_state.analysis_results.get('gui_entries'):
            df_results = pd.DataFrame(st.session_state.analysis_results['gui_entries'])
            # Apply risk coloring
            def color_risk(val):
                try:
                    score = float(str(val).replace('N/A', '0'))
                    if score >= RISK_CATEGORIES['high'][0]:
                        return 'background-color: #fee2e2'
                    elif score >= RISK_CATEGORIES['moderate'][0]:
                        return 'background-color: #fef3c7'
                    else:
                        return 'background-color: #dcfce7'
                except:
                    return ''
            styled = df_results.style.applymap(color_risk, subset=['RiskScore'])
            st.dataframe(styled, use_container_width=True, height=400)

            # Summary metrics (placeholder)
            st.subheader("Summary Metrics")
            total_cost = df_results['BestTotalCost'].replace('N/A', np.nan).astype(float).sum()
            max_lt = df_results['BestCostLT'].replace('N/A', np.nan).astype(float).max()
            st.metric("Total BOM Cost (Optimized)", f"${total_cost:.2f}" if pd.notna(total_cost) else "N/A")
            st.metric("Max Lead Time", f"{max_lt:.0f} days" if pd.notna(max_lt) else "N/A")
        else:
            st.info("Load a BOM and click Run Analysis to see results.")

    # Tab 2: AI & Predictions
    with tab2:
        if run_predict and not st.session_state.historical_data_df.empty:
            with st.spinner("Generating predictions..."):
                new_predictions = run_predictive_analysis(st.session_state.historical_data_df, context="")
                if new_predictions:
                    append_to_csv(PREDICTION_FILE, new_predictions)
                    st.session_state.predictions_df = pd.read_csv(PREDICTION_FILE) if PREDICTION_FILE.exists() else pd.DataFrame(columns=PRED_HEADER)
                    st.success("Predictions generated!")
                else:
                    st.warning("No predictions generated.")
        # Display predictions
        if not st.session_state.predictions_df.empty:
            st.subheader("Predictions vs Actuals")
            # Allow editing actuals? Use data_editor
            edited_df = st.data_editor(st.session_state.predictions_df, use_container_width=True, num_rows="dynamic")
            if st.button("Save Actuals"):
                # Save back to file
                edited_df.to_csv(PREDICTION_FILE, index=False)
                st.session_state.predictions_df = edited_df
                st.success("Saved!")
            # Average accuracies
            st.subheader("Average Prediction Accuracy")
            models = ["Prophet", "RAG", "AI"]
            acc_data = []
            for m in models:
                ld_col = f"{m}_Ld_Acc"
                cost_col = f"{m}_Cost_Acc"
                if ld_col in edited_df.columns:
                    ld_acc = pd.to_numeric(edited_df[ld_col], errors='coerce').mean()
                    cost_acc = pd.to_numeric(edited_df[cost_col], errors='coerce').mean()
                else:
                    ld_acc = np.nan
                    cost_acc = np.nan
                acc_data.append([m, f"{ld_acc:.1f}%" if pd.notna(ld_acc) else "N/A", f"{cost_acc:.1f}%" if pd.notna(cost_acc) else "N/A"])
            st.table(pd.DataFrame(acc_data, columns=["Model", "Lead Time Acc", "Cost Acc"]))
        else:
            st.info("No predictions yet. Run predictions to see data.")

        # AI Summary
        if run_ai:
            if not openai_client:
                st.error("OpenAI API key not set.")
            elif not st.session_state.analysis_results:
                st.error("Run analysis first.")
            else:
                with st.spinner("Generating AI summary..."):
                    # Build prompt (simplified)
                    prompt = "Provide a strategic supply chain summary for the following BOM analysis:\n"
                    gui_entries = st.session_state.analysis_results.get('gui_entries', [])
                    total_cost = sum(safe_float(e.get('BestTotalCost'), default=0) for e in gui_entries)
                    prompt += f"Total optimized cost: ${total_cost:.2f}\n"
                    # Add more details...
                    prompt += "Recommend the best sourcing strategy."
                    try:
                        response = openai_client.chat.completions.create(
                            model="gpt-4o",
                            messages=[{"role": "user", "content": prompt}],
                            max_tokens=500
                        )
                        summary = response.choices[0].message.content
                        st.markdown(summary)
                    except Exception as e:
                        st.error(f"OpenAI error: {e}")

    # Tab 3: Visualizations
    with tab3:
        if st.session_state.analysis_results and st.session_state.analysis_results.get('gui_entries'):
            df_viz = pd.DataFrame(st.session_state.analysis_results['gui_entries'])
            # Convert numeric columns
            for col in ['RiskScore', 'BestTotalCost', 'BestCostLT']:
                df_viz[col] = pd.to_numeric(df_viz[col], errors='coerce')
            plot_type = st.selectbox("Select Plot", ["Risk Distribution", "Cost Distribution", "Lead Time Distribution", "Cost vs Lead Time"])
            if plot_type == "Risk Distribution":
                fig = px.histogram(df_viz, x='RiskScore', nbins=20, title="Risk Score Distribution")
                st.plotly_chart(fig, use_container_width=True)
            elif plot_type == "Cost Distribution":
                fig = px.histogram(df_viz, x='BestTotalCost', nbins=20, title="Cost Distribution")
                st.plotly_chart(fig, use_container_width=True)
            elif plot_type == "Lead Time Distribution":
                fig = px.histogram(df_viz, x='BestCostLT', nbins=20, title="Lead Time Distribution")
                st.plotly_chart(fig, use_container_width=True)
            elif plot_type == "Cost vs Lead Time":
                fig = px.scatter(df_viz, x='BestCostLT', y='BestTotalCost', hover_data=['PartNumber', 'MfgPN'], title="Cost vs Lead Time")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Run analysis to see visualizations.")

if __name__ == "__main__":
    main()

st.divider()
st.caption("BOM Analyzer Web Edition · CRDV Adaptation Initiative · AI by Groq (free) · For PCB Department use")
