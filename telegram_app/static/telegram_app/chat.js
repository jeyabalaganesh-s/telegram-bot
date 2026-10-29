
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

    
    const fileInput = document.getElementById("media-file");
    const selectedFileLabel = document.getElementById("selected-file");

    if (fileInput) {
        fileInput.addEventListener("change", () => {
            const file = fileInput.files[0];

            if (selectedFileLabel) {
                selectedFileLabel.textContent = file
                    ? `Attachment: ${file.name}`
                    : "";
            }
        });
    }


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
        const file = fileInput?.files?.[0];

        if (!text && !file) return;

        if (text.length > 4096) {
            status.textContent = "Message must be 4096 characters or fewer.";
            return;
        }

        if (file && file.size > 20 * 1024 * 1024) {
            status.textContent = "File size must not exceed 20 MB.";
            return;
        }

        button.disabled = true;
        input.disabled = true;

        if (status) status.textContent = file ? "Uploading media..." : "Sending...";

        try {
            const csrfToken = getCsrfToken();
            let response;
            let result;

            if (file) {
                const data = new FormData();
                data.append("file", file);
                data.append("caption", text);

                response = await fetch(form.dataset.mediaUrl, {
                    method: "POST",
                    headers: {
                        "X-CSRFToken": csrfToken
                    },
                    credentials: "same-origin",
                    body: data
                });
            } else {
                response = await fetch(form.dataset.sendUrl, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrfToken
                    },
                    credentials: "same-origin",
                    body: JSON.stringify({ text })
                });
            }

            result = await response.json();

            if (!response.ok || result.ok !== true) {
                throw new Error(result.error || "Message could not be sent.");
            }

            // WebSocket may already have added this message.
            // addMessage() should deduplicate using its database ID.
            if (result.message) {
                addMessage({
                    ...result.message,
                    chat_id: result.message.chat_id ?? chatId
                });
            }

            input.value = "";

            if (fileInput) fileInput.value = "";
            if (selectedFileLabel) selectedFileLabel.textContent = "";

            if (status) status.textContent = file
                ? "Media sent successfully."
                : "Message sent.";

            input.focus();

        } catch (error) {
            console.error("Send failed:", error);
            if (status) status.textContent = error.message || "Something went wrong.";
        } finally {
            button.disabled = false;
            input.disabled = false;
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
