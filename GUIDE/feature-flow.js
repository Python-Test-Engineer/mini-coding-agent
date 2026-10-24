(() => {
  const stageData = document.getElementById("flow-data");
  const scenarioButtons = [...document.querySelectorAll("[data-scenario]")];
  const nodes = [...document.querySelectorAll("[data-node]")];
  const list = document.getElementById("event-list");
  const sample = document.getElementById("sample-output");
  const progress = document.getElementById("progress");
  const progressBar = document.querySelector("[role='progressbar']");
  const title = document.getElementById("step-title");
  const description = document.getElementById("step-description");
  const code = document.getElementById("step-code");
  const count = document.getElementById("step-count");
  const playButton = document.getElementById("play");
  let steps = JSON.parse(stageData.textContent);
  let stepIndex = -1;
  let timer = null;

  function stop() {
    if (timer !== null) window.clearInterval(timer);
    timer = null;
    playButton.textContent = "▶ Play";
  }

  function render() {
    const current = stepIndex >= 0 ? steps[stepIndex] : null;
    nodes.forEach((node) => node.classList.toggle("active", Boolean(current && current.nodes.includes(node.dataset.node))));
    list.replaceChildren();
    const eventItems = current ? current.events : ["Press Play or Next to follow this feature one step at a time."];
    eventItems.forEach((event, index) => {
      const item = document.createElement("li");
      item.classList.add("active");
      const bubble = document.createElement("span");
      bubble.className = "bubble";
      bubble.textContent = String(index + 1);
      const message = document.createElement("span");
      message.textContent = event;
      item.append(bubble, message);
      list.append(item);
    });
    if (current) {
      count.textContent = `Step ${stepIndex + 1} of ${steps.length}`;
      title.textContent = current.title;
      description.textContent = current.description;
      code.textContent = current.code;
      sample.textContent = current.sample;
    } else {
      count.textContent = `Ready · 0 of ${steps.length}`;
      title.textContent = "Press Play to explore this feature";
      description.textContent = "The active component and event trace will update as the animation moves through the implementation.";
      code.textContent = "agent → feature → UI / event log";
      sample.textContent = "The current event output will appear here.";
    }
    const percent = current ? Math.round(((stepIndex + 1) / steps.length) * 100) : 0;
    progress.style.width = `${percent}%`;
    progressBar.setAttribute("aria-valuenow", String(percent));
  }

  function advance() {
    if (stepIndex < steps.length - 1) {
      stepIndex += 1;
      render();
    } else stop();
  }

  function start() {
    if (timer !== null) return;
    if (stepIndex >= steps.length - 1) stepIndex = -1;
    playButton.textContent = "▶ Playing";
    advance();
    timer = window.setInterval(advance, 2500);
  }

  playButton.addEventListener("click", start);
  document.getElementById("pause").addEventListener("click", stop);
  document.getElementById("next").addEventListener("click", () => { stop(); advance(); });
  document.getElementById("back").addEventListener("click", () => { stop(); stepIndex = Math.max(-1, stepIndex - 1); render(); });
  document.getElementById("restart").addEventListener("click", () => { stop(); stepIndex = -1; render(); });

  scenarioButtons.forEach((button) => button.addEventListener("click", () => {
    stop();
    const scenario = document.getElementById(button.dataset.scenario);
    steps = JSON.parse(scenario.textContent);
    stepIndex = -1;
    scenarioButtons.forEach((other) => other.setAttribute("aria-pressed", String(other === button)));
    render();
  }));

  render();
})();
