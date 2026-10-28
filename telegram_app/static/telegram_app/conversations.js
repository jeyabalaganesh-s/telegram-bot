
document.addEventListener("DOMContentLoaded", () => {
    const status = document.getElementById("connection-status");
    const dot = document.getElementById("connection-dot");

    let socket;
    let reconnectTimer;

    function connect() {
        const scheme =
            window.location.protocol === "https:" ? "wss" : "ws";

        socket = new WebSocket(
            `${scheme}://${window.location.host}/ws/telegram/`
        );

        socket.onopen = () => {
            status.textContent = "Connected";
            dot.style.background = "#22c55e";
        };

        socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                if (data.chat_id && data.text) {
                    window.location.reload();
                }
            } catch (error) {
                console.error("Invalid WebSocket message", error);
            }
        };

        socket.onerror = () => {
            status.textContent = "Connection error";
            dot.style.background = "#ef4444";
        };

        socket.onclose = () => {
            status.textContent = "Reconnecting...";
            dot.style.background = "#f0ad4e";

            clearTimeout(reconnectTimer);
            reconnectTimer = setTimeout(connect, 3000);
        };
    }

    connect();
});
