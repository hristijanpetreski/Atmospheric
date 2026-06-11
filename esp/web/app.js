const $ = (id) => document.getElementById(id);
const form = $("setup-form");
const message = $("message");

async function request(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Device request failed");
  return data;
}

function setMessage(text, type = "") {
  message.textContent = text;
  message.className = type;
}

async function loadConfig() {
  const config = await request("/api/config");
  $("wifi-ssid").value = config.wifi.ssid;
  $("mqtt-host").value = config.mqtt.host;
  $("mqtt-port").value = config.mqtt.port;
  $("mqtt-topic").value = config.mqtt.topic;
  $("mqtt-username").value = config.mqtt.username;
  $("sampling-interval").value = config.sampling_interval;
  if (!config.wifi.password_set) {
    $("wifi-password-hint").textContent =
      "Enter the password for this network.";
  }
}

async function refreshStatus() {
  try {
    const status = await request("/api/status");
    const pulse = $("status-pulse");
    pulse.className = "pulse " + (status.wifi.connected ? "online" : "");
    $("status-title").textContent = status.wifi.connected
      ? "WiFi connected"
      : "Setup mode";
    $("status-detail").textContent = status.wifi.ip || "No network address";
    const reading = status.sensor.reading;
    if (reading) {
      $("temperature").textContent = reading.temperature.toFixed(2);
      $("humidity").textContent = reading.humidity.toFixed(2);
      $("pressure").textContent = reading.pressure.toFixed(2);
    }
  } catch {
    $("status-pulse").className = "pulse error";
    $("status-title").textContent = "Device unavailable";
    $("status-detail").textContent = "Trying again";
  }
}

$("scan-button").addEventListener("click", async (event) => {
  event.currentTarget.disabled = true;
  event.currentTarget.textContent = "Scanning...";
  try {
    const data = await request("/api/wifi");
    $("wifi-networks").replaceChildren(
      ...data.networks.map((ssid) =>
        Object.assign(document.createElement("option"), { value: ssid }),
      ),
    );
    setMessage(`${data.networks.length} networks found.`);
  } catch (error) {
    setMessage(error.message, "error");
  } finally {
    event.currentTarget.disabled = false;
    event.currentTarget.textContent = "Scan nearby";
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector("[type=submit]");
  button.disabled = true;
  setMessage("Validating and saving...");
  const payload = {
    wifi: {
      ssid: $("wifi-ssid").value,
      password: $("wifi-password").value,
    },
    mqtt: {
      host: $("mqtt-host").value,
      port: Number($("mqtt-port").value),
      topic: $("mqtt-topic").value,
      username: $("mqtt-username").value,
      password: $("mqtt-password").value,
    },
    sampling_interval: Number($("sampling-interval").value),
  };
  try {
    await request("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setMessage("Saved. The device is restarting now.", "success");
  } catch (error) {
    setMessage(error.message, "error");
    button.disabled = false;
  }
});

Promise.all([loadConfig(), refreshStatus()]).catch((error) =>
  setMessage(error.message, "error"),
);
setInterval(refreshStatus, 5000);
