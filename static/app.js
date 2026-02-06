document.getElementById("getTicket").onclick = async () => {
  const response = await fetch("/customers", {
    method: "POST"
  });

  const data = await response.json();

  document.getElementById("ticket").innerHTML = `
    <h2>Ticket: ${data.ticket_number}</h2>
    <p>People ahead: ${data.people_ahead}</p>
    <p>Estimated wait: ${data.estimated_wait_minutes} minutes</p>
  `;
};
