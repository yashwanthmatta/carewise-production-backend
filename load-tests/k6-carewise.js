import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  stages: [
    { duration: "30s", target: 50 },
    { duration: "1m", target: 200 },
    { duration: "30s", target: 0 },
  ],
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500"],
  },
};

const BASE_URL = __ENV.CAREWISE_BASE_URL || "http://localhost:8000";

export default function () {
  const health = http.get(`${BASE_URL}/health`);
  check(health, {
    "health is ok": (response) => response.status === 200,
  });
  sleep(1);
}
