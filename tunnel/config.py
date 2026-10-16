import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OMS_CSV = ROOT / "OMS Data_Feb24-Jan26_new.csv"
DATA = ROOT / "data"
TRUTH = DATA / "truth.json"
CUSTOMERS = DATA / "customers.csv"
RUNS = ROOT / "runs"

SITE_DATA = ROOT / "storefront" / "src" / "data"
PRODUCTS = SITE_DATA / "products.json"
VISUAL = SITE_DATA / "visual.json"
REVIEWS = SITE_DATA / "reviews.json"
TUNNEL = SITE_DATA / "tunnel.json"

SITE_URL = os.getenv("SITE_URL", "http://localhost:5173")
REGION = os.getenv("AWS_REGION", "us-east-1")
# Haiku 5.5 is not enabled on this Bedrock account, so Sonnet runs every role by default.
SHOPPER_MODEL = os.getenv("SHOPPER_MODEL", "us.anthropic.claude-sonnet-5-5")
ANALYST_MODEL = os.getenv("ANALYST_MODEL", "us.anthropic.claude-sonnet-5-5")
