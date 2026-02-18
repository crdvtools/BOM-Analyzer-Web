# Contributing to BOM Analyzer Web

Thank you for your interest in contributing! This project welcomes contributions from the PCB design, electronics engineering, and software communities.

---

## 🧭 Ways to Contribute

- **Bug Reports** — Found something broken? Open an issue
- **Feature Requests** — Have an idea? Share it as a GitHub Discussion or issue
- **Code Contributions** — Submit a pull request
- **Documentation** — Improve the README, add usage examples, fix typos
- **API Integrations** — Add support for additional suppliers (Arrow, Avnet, DigiKey, etc.)

---

## 🛠️ Development Setup

```bash
# 1. Fork the repository on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/bom-analyzer-web.git
cd bom-analyzer-web

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate     # Linux/macOS
venv\Scripts\activate        # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
streamlit run app.py
```

---

## 📥 Submitting a Pull Request

1. **Fork** the repository
2. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes** — keep commits focused and well-described
4. **Test your changes** locally with `streamlit run app.py`
5. **Push** your branch and open a Pull Request against `main`

### PR Guidelines

- Keep pull requests focused on a single feature or fix
- Include a clear description of what changed and why
- If adding a new API integration, include documentation on how to obtain credentials
- Do not commit API keys, `.env` files, or any credentials

---

## 🐛 Reporting Bugs

Open an issue and include:
- Steps to reproduce the problem
- Expected behavior vs. actual behavior
- Any error messages or screenshots
- Python version and OS (for local installs)

---

## 💡 Feature Requests

Open an issue with the label `enhancement` and describe:
- What you want the tool to do
- Why it would benefit PCB/procurement teams
- Any relevant supplier API documentation

---

## 📐 Code Style

- Follow existing code style (functional Python, Streamlit patterns)
- Keep supplier API functions in the same format as `search_mouser()` and `search_nexar()` for consistency
- Add docstrings to new functions
- Use `safe_float()` for all numeric conversions from API responses

---

## 🔌 Adding a New Supplier API

If you're adding support for a new supplier (e.g., Arrow, Avnet, DigiKey), follow this pattern:

```python
def search_SUPPLIER(part_number, api_key):
    """
    Fetch from SUPPLIER API.
    Returns standardized result dict or None.
    """
    if not api_key:
        return None
    try:
        # ... API call logic ...
        return {
            "Source":                 "SUPPLIER NAME",
            "SourcePartNumber":       "...",
            "ManufacturerPartNumber": "...",
            "Manufacturer":           "...",
            "Description":            "...",
            "Stock":                  int(...),
            "LeadTimeDays":           int_or_nan,
            "MinOrderQty":            int(...),
            "Pricing":                [{"qty": int, "price": float}, ...],
            "CountryOfOrigin":        "...",
            "NormallyStocking":       True,
            "Discontinued":           False,
            "EndOfLife":              False,
            "DatasheetUrl":           "...",
        }
    except Exception:
        return None
```

Then add it to `get_part_data_parallel()` and add the corresponding API key input in the sidebar.

---

## 📄 License

By contributing, you agree that your contributions will be licensed under the project's [MIT License](LICENSE).

---

## 🙏 Thank You

This project was initiated by Norman Emmanuel D. Cordova, IPC Certified Interconnect Designer (CID), to make supply chain tooling more accessible for small PCB teams. Every contribution — big or small — helps the community.
