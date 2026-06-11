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

function renderNetworks(networks) {
  const results = $("network-results");
  const list = $("network-list");
  const datalist = $("wifi-networks");
  list.textContent = "";
  datalist.textContent = "";
  $("network-count").textContent = String(networks.length);

  networks.forEach((ssid) => {
    const option = document.createElement("option");
    option.value = ssid;
    datalist.appendChild(option);

    const row = document.createElement("div");
    row.className = "network-result";

    const name = document.createElement("span");
    name.textContent = ssid;
    name.title = ssid;

    const select = document.createElement("button");
    select.type = "button";
    select.className = "select-network";
    select.textContent = "Select";
    select.setAttribute("data-ssid", ssid);

    row.appendChild(name);
    row.appendChild(select);
    list.appendChild(row);
  });

  results.hidden = false;
}

$("network-list").addEventListener("click", (event) => {
  const button = event.target.closest(".select-network");
  if (!button) return;
  $("wifi-ssid").value = button.getAttribute("data-ssid");
  $("wifi-password").focus();
  setMessage("Selected " + button.getAttribute("data-ssid") + ".");
});

$("scan-button").addEventListener("click", async () => {
  const button = $("scan-button");
  button.disabled = true;
  button.textContent = "Scanning...";
  try {
    const data = await request("/api/wifi");
    renderNetworks(data.networks);
    setMessage(data.networks.length + " networks found.");
  } catch (error) {
    setMessage(error.message, "error");
  }
  button.disabled = false;
  button.textContent = "Scan";
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
