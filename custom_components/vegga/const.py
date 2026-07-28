DOMAIN = "vegga"

CONF_DEVICE_ID = "device_id"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 30
HISTORY_REFRESH_MINUTES = 30
HISTORY_LOOKBACK_DAYS = 60
HISTORY_PAGE_SIZE = 2000
ANOMALY_WARNING_PERCENT = 15.0
ANOMALY_ALARM_PERCENT = 25.0
MIN_BASELINE_SAMPLES = 5
BASELINE_SAMPLE_COUNT = 20

API_BASE_URL = "https://vegga-prod.azure-api.net/agronic/api/v1"
HISTORY_BASE_URL = "https://vegga-prod.azure-api.net/irrigation-control-service"
CORE_BASE_URL = "https://vegga-prod.azure-api.net/core-service"
LOGIN_URL = "https://vegga-prod.azure-api.net/login"
CLIENT_ID = "70aa1ea0-8fdb-4edc-a80e-10a3da9b4146"
OAUTH_SCOPE = f"openid {CLIENT_ID} offline_access"
