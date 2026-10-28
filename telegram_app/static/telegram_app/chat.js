
document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("send-message-form");
    const input = document.getElementById("outgoing-message");
    const history = document.getElementById("chat-history");
    const status = document.getElementById("send-status");
    const button = document.getElementById("send-button");

    const connectionStatus = document.getElementById("connection-status");
    const connectionDot = document.getElementById("connection-dot");

    if (!form || !input || !history || !button) {
        console.error("Chat elements are missing from chat.html.");
        return;
    }

    const csrfInput = form.querySelector(
        'input[name="csrfmiddlewaretoken"]'
    );

    const chatId = String(history.dataset.chatId || "");
    const sendUrl = form.dataset.sendUrl;

    let socket = null;
    let reconnectTimer = null;
    let manuallyClosed = false;

    // Update the sidebar connection indicator.
    function setConnectionStatus(text, color) {
        if (connectionStatus) {
            connectionStatus.textContent = text;
        }

        if (connectionDot) {
            connectionDot.style.backgroundColor = color;
        }
    }

    // Scroll to the newest message.
    function scrollToBottom() {
        history.scrollTop = history.scrollHeight;
    }

    // Check whether a message is already displayed.
    function messageExists(messageId) {
        if (messageId === undefined || messageId === null) {
            return false;
        }

        return Array.from(
            history.querySelectorAll("[data-message-id]")
        ).some(
            element =>
                element.dataset.messageId === String(messageId)
        );
    }

    // Add a message safely to the chat window.
    
function addMessage(message) {
    if (!message || !message.text) return;

    if (
        message.chat_id !== undefined &&
        String(message.chat_id) !== String(history.dataset.chatId)
    ) {
        return;
    }

    // Prevent duplicate messages.
    if (message.id !== undefined && message.id !== null) {
        const existing = Array.from(
            history.querySelectorAll("[data-message-id]")
        ).some(
            element =>
                element.dataset.messageId === String(message.id)
        );

        if (existing) return;
    }

    const emptyState = history.querySelector(".empty-state");
    if (emptyState) emptyState.remove();

    const outgoing = message.direction === "outgoing";

    const bubble = document.createElement("div");
    bubble.className = `message-bubble ${outgoing ? "outgoing" : "incoming"}`;

    if (message.id !== undefined && message.id !== null) {
        bubble.dataset.messageId = String(message.id);
    }

    // Match the bubble appearance used in the chat page.
    bubble.style.cssText = `
        padding: 12px 16px;
        margin: 10px 0;
        border-radius: 12px;
        overflow-wrap: anywhere;
        white-space: normal;
        width: ${outgoing ? "75%" : "75%"};
        ${outgoing
            ? "margin-left: auto; margin-right: 0; background: #eaf4ff;"
            : "margin-left: 0; margin-right: auto; background: #f1f5f9;"}
        box-sizing: border-box;
    `;

    const sender = document.createElement("strong");
    sender.textContent = outgoing ? "You" : "Bala";
    sender.style.cssText = "display:block;color:#64748b;font-size:13px;margin-bottom:8px;";

    const body = document.createElement("div");
    body.className = "message-text";
    body.textContent = message.text;
    body.style.cssText = "white-space:pre-wrap;overflow-wrap:anywhere;margin-bottom:10px;";

    const timestamp = document.createElement("small");
    timestamp.style.cssText = "display:block;color:#94a3b8;font-size:12px;";

    if (message.created_at) {
        timestamp.textContent = new Date(message.created_at)
            .toLocaleString("en-GB", {
                day: "2-digit",
                month: "short",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit",
                hour12: false
            });
    } else {
        timestamp.textContent = new Date().toLocaleString();
    }

    bubble.append(sender, body, timestamp);
    history.appendChild(bubble);

    history.scrollTop = history.scrollHeight;
}


    // Read the CSRF token safely.
    function getCsrfToken() {
        if (csrfInput) {
            return csrfInput.value;
        }

        const csrfCookie = document.cookie
            .split("; ")
            .find(cookie => cookie.startsWith("csrftoken="));

        return csrfCookie
            ? decodeURIComponent(csrfCookie.substring("csrftoken=".length))
            : "";
    }

    // Connect to Django Channels.
    function connectWebSocket() {
        if (manuallyClosed) return;

        const protocol =
            window.location.protocol === "https:" ? "wss:" : "ws:";

        socket = new WebSocket(
            `${protocol}//${window.location.host}/ws/telegram/`
        );

        socket.onopen = () => {
            setConnectionStatus("Connected", "#22c55e");
        };

        socket.onmessage = event => {
            try {
                const message = JSON.parse(event.data);
                addMessage(message);
            } catch (error) {
                console.error("Could not parse WebSocket message:", error);
            }
        };

        socket.onerror = () => {
            setConnectionStatus("Connection error", "#ef4444");
        };

        socket.onclose = event => {
            if (event.code === 4401) {
                setConnectionStatus("Please log in again", "#ef4444");
                return;
            }

            setConnectionStatus("Reconnecting...", "#f0ad4e");

            if (!manuallyClosed) {
                clearTimeout(reconnectTimer);
                reconnectTimer = setTimeout(connectWebSocket, 3000);
            }
        };
    }

    // Send a message through Django to Telegram.
    form.addEventListener("submit", async event => {
        event.preventDefault();

        const text = input.value.trim();

        if (!text) return;

        if (text.length > 4096) {
            if (status) {
                status.textContent =
                    "Message must be 4096 characters or fewer.";
            }
            return;
        }

        button.disabled = true;
        input.disabled = true;

        if (status) {
            status.textContent = "Sending...";
        }

        try {
            const response = await fetch(sendUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCsrfToken()
                },
                credentials: "same-origin",
                body: JSON.stringify({ text })
            });

            const result = await response.json();

            // Supports either response key while your Django view is aligned.
            if (
                !response.ok ||
                !(result.success === true || result.ok === true)
            ) {
                throw new Error(
                    result.error || "Message could not be sent."
                );
            }

            if (result.message) {
                addMessage({
                    ...result.message,
                    id: result.message.id,
                    chat_id: result.message.chat_id ?? chatId,
                    direction: "outgoing",
                    text: result.message.text || text
                });
            } else {
                // Fallback if the view doesn't return a message object.
                addMessage({
                    chat_id: chatId,
                    direction: "outgoing",
                    text
                });
            }

            input.value = "";

            if (status) {
                status.textContent = "Message sent.";
            }

            input.focus();
        } catch (error) {
            console.error("Failed to send message:", error);

            if (status) {
                status.textContent =
                    error.message || "Something went wrong.";
            }
        } finally {
            button.disabled = false;
            input.disabled = false;
            input.focus();
        }
    });

    // Enter sends a message when using a textarea.
    // Shift+Enter inserts a new line.
    input.addEventListener("keydown", event => {
        if (
            input.tagName === "TEXTAREA" &&
            event.key === "Enter" &&
            !event.shiftKey
        ) {
            event.preventDefault();
            form.requestSubmit();
        }
    });

    scrollToBottom();
    connectWebSocket();

    window.addEventListener("beforeunload", () => {
        manuallyClosed = true;
        clearTimeout(reconnectTimer);

        if (socket) {
            socket.close();
        }
    });
});
