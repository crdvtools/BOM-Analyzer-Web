# 🔬 BOM Analyzer Web

> **Open-source PCB supply chain analysis tool** — real-time pricing, multi-factor risk scoring, and AI-powered insights for electronics manufacturing teams.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Built%20with-Streamlit-red)](https://streamlit.io)
[![Deploy on Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io)

---

## 📖 About

**BOM Analyzer Web** is a browser-based supply chain optimization tool designed for PCB (Printed Circuit Board) engineering and procurement teams. It converts a Bill of Materials CSV into actionable purchasing intelligence — fetching live supplier data, scoring component risk, estimating tariff impacts, and generating AI executive summaries.

This project is a **Streamlit web conversion** of [Tyler Allen's BOM Analyzer](https://github.com/ctylerallen/BOM_Analyzer) desktop application, adapted and extended for team-wide web deployment with free-tier AI integration via [Groq](https://console.groq.com).

### ✨ Key Features

| Feature | Description |
|---|---|
| 📡 **Live Supplier Data** | Real-time pricing, stock, and lead times from Mouser & Nexar/Octopart |
| 💰 **Price Break Optimization** | MOQ-aware buy-up logic finds the true optimal order quantity |
| ⚠️ **5-Factor Risk Scoring** | Weighted scoring across Sourcing, Stock, Lead Time, Lifecycle, and Geographic risk |
| 🌍 **Tariff Estimation** | Country-of-origin tariff impact with per-country custom rates |
| 📊 **4 Purchasing Strategies** | Lowest Cost (Strict), Lowest Cost (In-Stock), Fastest Lead Time, Optimized (Cost+LT) |
| 🤖 **AI Executive Summary** | Groq-powered (free) procurement recommendations for team leads |
| 📤 **Full CSV Export** | Export any strategy or the full analysis to CSV |

---

## 🚀 Quick Start (No Installation — Cloud Deploy)

> **Deploy for your whole team in under 30 minutes, completely free.**

### Step 1 — Get Your Free API Keys

| Service | Link | Purpose | Cost |
|---|---|---|---|
| **Groq** | [console.groq.com](https://console.groq.com) | AI Summary | Free |
| **Mouser** | [mouser.com/api-search](https://www.mouser.com/api-search/) | Pricing & Stock | Free |
| **Nexar** | [nexar.com](https://nexar.com) | Pricing & Stock (backup) | Free tier |

> You can start with **just the Groq key** — the app runs without supplier keys (results will show "Not Found" until supplier keys are added).

### Step 2 — Fork and Deploy

1. **Fork this repository** — click the `Fork` button at the top right of this page
2. Go to **[share.streamlit.io](https://share.streamlit.io)** and sign in with GitHub
3. Click **"New app"** → select your forked repo → set main file to `app.py`
4. Click **"Deploy"** — your app goes live at a shareable URL

### Step 3 — Share with Your Team

Share the Streamlit URL with your PCB team. No installation required — works in any browser.

---

## 💻 Local Development

### Prerequisites

- Python 3.9 or higher
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/crdvtools/bom-analyzer-web.git
cd bom-analyzer-web

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

The app will open at `http://localhost:8501`.

---

## 📋 BOM CSV Format

Upload a CSV with the following columns:

| Column | Required | Description |
|---|---|---|
| `Part Number` | ✅ Yes | Manufacturer part number or distributor SKU |
| `Quantity` | ✅ Yes | Quantity per finished unit (not total) |
| `Manufacturer` | Optional | Improves API matching accuracy |
| `Description` | Optional | Used as fallback if API returns no description |

**Example:**
```csv
Part Number,Quantity,Manufacturer,Description
LM358DR,2,Texas Instruments,Op-Amp Dual
RMCF0402FT100K,10,Stackpole,Resistor 100K 0402
GRM188R71C104KA01D,4,Murata,Cap 100nF 0402
```

A downloadable template is available directly inside the app.

---

## ⚙️ Configuration

All settings are accessible in the sidebar without editing any code:

| Setting | Default | Description |
|---|---|---|
| Total Units to Build | 100 | Multiplies BOM qty to get total component need |
| Target Lead Time | 56 days | Max acceptable lead time for Optimized strategy |
| Max Cost Premium % | 15% | How much more than cheapest is acceptable |
| Cost / LT Weight | 0.50 / 0.50 | Trade-off between cost and speed in Optimized |
| Buy-Up Threshold % | 1% | Allow minor cost increase to hit a price break |
| Custom Tariff Rates | — | Per-country tariff override (blank = defaults) |

---

## 📐 Risk Scoring Methodology

Risk scores are calculated on a **0–10 scale** using weighted factors:

| Factor | Weight | Scoring Logic |
|---|---|---|
| **Sourcing** | 30% | 0 sources = 10, 1 source = 7, 2 sources = 4, 3+ = 0 |
| **Lifecycle** | 30% | EOL/Discontinued = 10, Active = 0 |
| **Stock** | 15% | Stock gap = 8, tight stock = 4, sufficient = 0 |
| **Lead Time** | 15% | >90 days = 7, >45 days = 4, ≤45 days = 1, in-stock = 0 |
| **Geographic** | 10% | Russia=9, China=7, Taiwan=5, India=5, USA/Japan/Germany=1 |

**Risk Categories:**
- 🔴 **High Risk:** Score ≥ 6.6
- 🟡 **Moderate Risk:** Score 3.6 – 6.5
- 🟢 **Low Risk:** Score < 3.6

---

## 🤖 AI Summary (Groq — Free)

The AI executive summary feature uses [Groq's API](https://console.groq.com) with LLaMA 3.3 70B — completely free, no credit card required. It analyzes your BOM results and generates:

1. **Executive Summary** — 2–3 sentence build-readiness overview
2. **Critical Risks** — specific part numbers needing immediate attention
3. **Top 3 Procurement Recommendations** — actionable steps
4. **Cost Optimization Opportunities** — price break and tariff insights
5. **Recommended Strategy** — which of the 4 strategies best fits your situation

---

## 🔌 API Integrations

| Supplier | API Docs | Auth Method | Rate Limit |
|---|---|---|---|
| **Mouser** | [mouser.com/api-search](https://www.mouser.com/api-search/) | API Key | 1,000/day (free) |
| **Nexar (Octopart)** | [nexar.com/api](https://nexar.com/api) | OAuth2 Client Credentials | Free tier |
| **Groq** | [console.groq.com/docs](https://console.groq.com/docs) | API Key | Generous free tier |

> **Note:** DigiKey integration requires OAuth with a localhost callback and is not compatible with cloud deployment. Mouser and Nexar provide equivalent coverage for most use cases.

---

## 🏗️ Project Structure

```
bom-analyzer-web/
├── app.py                  # Main Streamlit application
├── requirements.txt        # Python dependencies
├── .streamlit/
│   └── config.toml         # Streamlit theme and server config
├── README.md               # This file
├── LICENSE                 # MIT License
└── CONTRIBUTING.md         # Contribution guidelines
```

---

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a pull request.

Ideas for future enhancements:
- [ ] DigiKey integration via server-side OAuth proxy
- [ ] Arrow Electronics API support
- [ ] Avnet API support
- [ ] Prophet-based lead time forecasting (ported from desktop app)
- [ ] Historical analysis tracking across sessions
- [ ] ERP/PLM CSV export templates (SAP, Oracle)
- [ ] Password-protected team deployment
- [ ] Slack/Teams notifications for high-risk parts

---

## 🙏 Acknowledgments

- **Original Desktop Application:** [Tyler Allen (@ctylerallen)](https://github.com/ctylerallen/BOM_Analyzer) — BOM Analyzer v1.0.0
- **Web Adaptation Initiated By:** Norman Emmanuel D. Cordova, IPC Certified Interconnect Designer (CID) — PCB Department Lead
- **AI Integration:** [Groq](https://groq.com) — LLaMA 3.3 70B (free tier)
- **Supplier Data:** [Mouser Electronics](https://mouser.com) · [Nexar / Octopart](https://nexar.com)
- **Deployment:** [Streamlit Community Cloud](https://streamlit.io/cloud)

---

## 📄 License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for full terms.

You are free to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of this software, provided the original copyright notice is retained.

---

## ⚠️ Disclaimer

This tool is provided for informational and procurement planning purposes. Pricing, stock, and lead time data is fetched live from third-party APIs and may not reflect final purchase conditions. Always verify supplier data before placing orders. The authors are not responsible for purchasing decisions made based on this tool.

---

<div align="center">

**Made with ❤️ for the PCB community**

[crdvtools](https://github.com/crdvtools) · Initiated by Norman Emmanuel D. Cordova, IPC CID

</div>
