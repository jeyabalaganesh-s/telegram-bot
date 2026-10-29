
document.addEventListener("DOMContentLoaded", () => {
    const messageList = document.getElementById("message-list");
    const emptyState = document.getElementById("empty-state");
    const messageCount = document.getElementById("message-count");
    const connectionValue = document.getElementById("connection-value");
    const connectionStatus = document.getElementById("connection-status");
    const clearButton = document.getElementById("clear-button");

    if (!messageList) return;

    const historyUrl = messageList.dataset.historyUrl;

    const renderedIds = new Set();

    let totalCount = 0;
    let socket = null;
    let reconnectTimer = null;
    let manuallyCleared = false;

    // Safely create text elements.
    function createTextElement(tag, className, text) {
        const element = document.createElement(tag);
        element.className = className;
        element.textContent = text || "";
        return element;
    }

    function formatDate(value) {
        if (!value) return "";

        const date = new Date(value);

        if (Number.isNaN(date.getTime())) return "";

        return date.toLocaleString([], {
            dateStyle: "medium",
            timeStyle: "short",
        });
    }

    function getMessageText(message) {
        const text = (message.text || "").trim();
        const mediaType = (message.media_type || "text").toLowerCase();

        if (text) return text;

        if (mediaType === "photo") return "📷 Photo";
        if (mediaType === "video") return "🎥 Video";
        if (mediaType === "voice") return "🎤 Voice message";
        if (mediaType === "audio") return "🎵 Audio";
        if (mediaType === "document") return "📎 Document";
        if (mediaType === "sticker") return "🎭 Sticker";
        if (mediaType === "animation") return "🎞️ Animation";
        if (mediaType === "text") return "(Empty message)";

        return "📎 " + mediaType;
    }

    function updateEmptyState() {
        if (!emptyState) return;

        emptyState.style.display =
            messageList.children.length === 0 ? "" : "none";
    }

    function updateCount(value) {
        totalCount = Math.max(0, Number(value) || 0);

        if (messageCount) {
            messageCount.textContent = totalCount.toLocaleString();
        }
    }

    function renderMessage(message, prepend = false) {
        // Ignore outgoing messages on the incoming-message dashboard.
        if (
            message.direction &&
            message.direction !== "incoming"
        ) {
            return false;
        }

        // Database messages have a primary key in message.id.
        const id = message.id;

        if (id !== undefined && id !== null) {
            const key = String(id);

            if (renderedIds.has(key)) return false;

            renderedIds.add(key);
        }

        const card = document.createElement("article");
        card.className = "message-card";

        if (id !== undefined && id !== null) {
            card.dataset.messageId = String(id);
        }

        const header = document.createElement("div");
        header.className = "message-header";

        const sender = createTextElement(
            "strong",
            "message-sender",
            message.display_name ||
                (message.username
                    ? "@" + message.username
                    : String(message.chat_id || "Telegram user"))
        );

        const timestamp = createTextElement(
            "span",
            "message-time",
            formatDate(message.created_at)
        );

        header.append(sender, timestamp);

        const body = createTextElement(
            "p",
            "message-text",
            getMessageText(message)
        );

        card.append(header, body);

        // Add the Telegram username or chat ID as secondary information.
        const details = message.username
            ? "@" + message.username
            : message.chat_id
                ? "Chat ID: " + message.chat_id
                : "";

        if (details) {
            card.append(
                createTextElement("small", "message-details", details)
            );
        }

        if (prepend) {
            messageList.prepend(card);
        } else {
            messageList.append(card);
        }

        updateEmptyState();
        return true;
    }

    // Load messages already stored in Django's database.
    async function loadDatabaseMessages() {
        if (!historyUrl) {
            console.error("Database history URL is missing.");
            return;
        }

        try {
            const response = await fetch(historyUrl, {
                method: "GET",
                headers: {
                    Accept: "application/json",
                },
                credentials: "same-origin",
            });

            if (response.status === 401 || response.status === 403) {
                throw new Error("Please log in to view dashboard messages.");
            }

            if (!response.ok) {
                throw new Error(
                    "Could not load messages. HTTP " + response.status
                );
            }

            const result = await response.json();

            if (!result.success || !Array.isArray(result.messages)) {
                throw new Error("Invalid message history response.");
            }

            // The API returns newest first. Render oldest to newest.
            const messages = [...result.messages].reverse();

            messages.forEach((message) => {
                renderMessage(message);
            });

            // This count includes all saved incoming messages, not just
            // the 100 most recent messages shown in the dashboard.
            updateCount(result.total_count);

        } catch (error) {
            console.error("Database message loading failed:", error);
        }
    }

    function setConnectionStatus(connected) {
        const text = connected ? "Connected" : "Disconnected";

        if (connectionValue) {
            connectionValue.textContent = text;
        }

        if (connectionStatus) {
            connectionStatus.textContent = text;
        }
    }

    function connectWebSocket() {
        if (
            socket &&
            (
                socket.readyState === WebSocket.OPEN ||
                socket.readyState === WebSocket.CONNECTING
            )
        ) {
            return;
        }

        const protocol =
            window.location.protocol === "https:" ? "wss:" : "ws:";

        const socketUrl =
            `${protocol}//${window.location.host}/ws/telegram/`;

        socket = new WebSocket(socketUrl);

        socket.onopen = () => {
            console.log("Dashboard WebSocket connected.");
            setConnectionStatus(true);
        };

        socket.onmessage = (event) => {
            try {
                const payload = JSON.parse(event.data);

                // Support both {id, ...} and {data: {id, ...}} payloads.
                const message = payload.data || payload;

                if (
                    message.direction &&
                    message.direction !== "incoming"
                ) {
                    return;
                }

                // If a message was already loaded from the database,
                // renderMessage returns false and won't count it twice.
                const added = renderMessage(message, true);

                if (added) {
                    updateCount(totalCount + 1);
                }

            } catch (error) {
                console.error("Invalid WebSocket message:", error);
            }
        };

        socket.onerror = (error) => {
            console.error("Dashboard WebSocket error:", error);
        };

        socket.onclose = (event) => {
            setConnectionStatus(false);

            // 4401 is used by the consumer when authentication fails.
            if (event.code === 4401) {
                console.warn("WebSocket authentication required.");
                return;
            }

            clearTimeout(reconnectTimer);

            reconnectTimer = setTimeout(() => {
                connectWebSocket();
            }, 3000);
        };
    }

    // Clear only the visible dashboard list.
    // This does not delete records from the database.
    if (clearButton) {
        clearButton.addEventListener("click", () => {
            messageList.replaceChildren();
            renderedIds.clear();
            manuallyCleared = true;
            updateEmptyState();

            // Keep the database-wide count unchanged.
        });
    }

    // Start the WebSocket immediately so new messages aren't missed
    // while the database history is being fetched.
    connectWebSocket();
    loadDatabaseMessages();
});
