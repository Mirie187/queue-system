document.getElementById("finish").onclick = async () => {
  const counter = document.getElementById("counter").value;

  const response = await fetch(`/counters/${counter}/finish`, {
    method: "POST"
  });

  const data = await response.json();

  document.getElementById("result").innerText = data.message;
};
