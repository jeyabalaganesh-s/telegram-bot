
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
    if (!message) return;

    // Ignore messages belonging to another conversation.
    if (
        message.chat_id !== undefined &&
        String(message.chat_id) !== String(history.dataset.chatId)
    ) {
        return;
    }

    // Prevent duplicate messages from WebSocket and HTTP responses.
    if (messageExists(message.id)) return;

    // Allow media-only messages without text or captions.
    const hasText = Boolean(message.text);
    const hasMedia = Boolean(message.media_url);

    if (!hasText && !hasMedia) return;

    const emptyState = history.querySelector(".empty-state");
    if (emptyState) emptyState.remove();

    const outgoing = message.direction === "outgoing";

    const bubble = document.createElement("div");
    bubble.className = `message-bubble ${
        outgoing
            ? "message-bubble--outgoing"
            : "message-bubble--incoming"
    }`;

    if (message.id !== undefined && message.id !== null) {
        bubble.dataset.messageId = String(message.id);
    }

    const sender = document.createElement("strong");
    sender.className = "message-sender";
    sender.textContent = outgoing ? "You" : "Bala";
    bubble.appendChild(sender);

    // Render text or caption when present.
    if (hasText) {
        const body = document.createElement("p");
        body.className = "message-content";
        body.textContent = message.text;
        bubble.appendChild(body);
    }

    // Render media received through the WebSocket.
    if (hasMedia) {
        const media = document.createElement("div");
        media.className = "message-media";

        const url = message.media_url;
        const type = message.media_type || "document";

        if (type === "photo" || type === "sticker") {
            const link = document.createElement("a");
            link.href = url;
            link.target = "_blank";
            link.rel = "noopener noreferrer";

            const img = document.createElement("img");
            img.src = url;
            img.alt = type === "photo"
                ? "Telegram photo"
                : "Telegram sticker";
            img.loading = "lazy";

            link.appendChild(img);
            media.appendChild(link);

        } else if (
            ["video", "animation", "video_note"].includes(type)
        ) {
            const video = document.createElement("video");
            video.controls = true;
            video.preload = "metadata";

            const source = document.createElement("source");
            source.src = url;

            video.appendChild(source);
            media.appendChild(video);

        } else if (["audio", "voice"].includes(type)) {
            const audio = document.createElement("audio");
            audio.controls = true;
            audio.preload = "metadata";
            audio.src = url;
            media.appendChild(audio);

        } else {
            const link = document.createElement("a");
            link.href = url;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            link.textContent = "View or download attachment";
            media.appendChild(link);
        }

        bubble.appendChild(media);
    }

    const timestamp = document.createElement("small");
    timestamp.className = "message-date";

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
    }

    bubble.appendChild(timestamp);
    history.appendChild(bubble);

    scrollToBottom();
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
