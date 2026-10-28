// Only file you edit to switch between fake and real data.
window.CONFIG = {
  // For the phone demo, replace with the Backend laptop's Wi-Fi IP, e.g. "http://192.168.1.12:8000"
  API_BASE: "http://127.0.0.1:8000",
  // true = Dashboard reads sample_reports.json. Set to false when Developer B's GET /reports works.
  USE_SAMPLE: false,
  // Map starting point (matches the sample data)
  CENTER: [13.6588, 77.2101],
  REFRESH_MS: 5000
};
