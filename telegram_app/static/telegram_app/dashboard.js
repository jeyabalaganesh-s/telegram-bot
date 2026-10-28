
const statusText = document.getElementById("connection-status");
const connectionValue = document.getElementById("connection-value");
const messageCount = document.getElementById("message-count");
const messageList = document.getElementById("message-list");
const emptyState = document.getElementById("empty-state");
const clearButton = document.getElementById("clear-button");
const statusDot = document.querySelector(".sidebar-bottom .status-dot");
const botDot = document.querySelector(".bot-badge .status-dot");

let totalMessages = 0;
let socket;
let reconnectTimer;
let reconnectDelay = 1000;

function updateStatus(connected) {
    statusText.textContent = connected ? "Connected" : "Disconnected";
    connectionValue.textContent = connected ? "Connected" : "Disconnected";

    statusDot.style.background = connected ? "#28c76f" : "#ea5455";
    botDot.style.background = connected ? "#28c76f" : "#ea5455";
}

function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${window.location.host}/ws/telegram/`;

    socket = new WebSocket(url);

    socket.addEventListener("open", () => {
        updateStatus(true);
        reconnectDelay = 1000;
        console.log("JEMI WebSocket connected");
    });

    socket.addEventListener("message", (event) => {
        try {
            const data = JSON.parse(event.data);
            displayMessage(data);
        } catch (error) {
            console.error("Invalid WebSocket message:", error);
        }
    });

    socket.addEventListener("close", () => {
        updateStatus(false);
        scheduleReconnect();
    });

    socket.addEventListener("error", () => {
        updateStatus(false);
        socket.close();
    });
}

function scheduleReconnect() {
    if (reconnectTimer) return;

    reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connectWebSocket();
        reconnectDelay = Math.min(reconnectDelay * 2, 30000);
    }, reconnectDelay);
}

function displayMessage(data) {
    emptyState.hidden = true;

    const card = document.createElement("article");
    card.className = "message-card";

    const top = document.createElement("div");
    top.className = "message-top";

    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.textContent = (data.username || "U").charAt(0).toUpperCase();

    const senderBlock = document.createElement("div");

    const sender = document.createElement("div");
    sender.className = "sender";
    sender.textContent = data.username
        ? `@${data.username}`
        : "Telegram user";

    const chatId = document.createElement("div");
    chatId.className = "chat-id";
    chatId.textContent = `Chat ID: ${data.chat_id ?? "Unknown"}`;

    senderBlock.append(sender, chatId);

    const time = document.createElement("div");
    time.className = "message-time";

    const date = data.date
        ? new Date(data.date * 1000)
        : new Date();

    time.textContent = date.toLocaleTimeString();

    top.append(avatar, senderBlock, time);

    const messageText = document.createElement("p");
    messageText.className = "message-text";
    messageText.textContent = data.text || "[Non-text message]";

    card.append(top, messageText);
    messageList.prepend(card);

    totalMessages += 1;
    messageCount.textContent = totalMessages;
}

clearButton.addEventListener("click", () => {
    messageList.replaceChildren();
    totalMessages = 0;
    messageCount.textContent = "0";
    emptyState.hidden = false;
});

connectWebSocket();
