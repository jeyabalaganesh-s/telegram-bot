
document.addEventListener("DOMContentLoaded", () => {
    // ==========================================
    // DOM ELEMENTS
    // ==========================================
    const form = document.getElementById("send-message-form");
    const input = document.getElementById("outgoing-message");
    const history = document.getElementById("chat-history");
    const status = document.getElementById("send-status");
    const button = document.getElementById("send-button");

    const connectionStatus = document.getElementById("connection-status");
    const connectionDot = document.getElementById("connection-dot");

    const fileInput = document.getElementById("media-file");
    const selectedFileLabel = document.getElementById("selected-file");

    const conversationList = document.getElementById(
        "chat-conversation-list"
    );

    if (!form || !input || !history || !button) {
        console.error("Required chat elements are missing.");
        return;
    }

    const csrfInput = form.querySelector(
        'input[name="csrfmiddlewaretoken"]'
    );

    const chatId = String(history.dataset.chatId || "");
    const sendUrl = form.dataset.sendUrl;
    const mediaUrl = form.dataset.mediaUrl;

    let socket = null;
    let reconnectTimer = null;
    let manuallyClosed = false;

    // ==========================================
    // CONNECTION STATUS
    // ==========================================
    function setConnectionStatus(text, color) {
        if (connectionStatus) {
            connectionStatus.textContent = text;
        }

        if (connectionDot) {
            connectionDot.style.backgroundColor = color;
        }
    }

    // ==========================================
    // MESSAGE UTILITIES
    // ==========================================
    function scrollToBottom() {
        history.scrollTop = history.scrollHeight;
    }

    function messageExists(messageId) {
        if (messageId === undefined || messageId === null) {
            return false;
        }

        return Array.from(
            history.querySelectorAll("[data-message-id]")
        ).some(element => {
            return element.dataset.messageId === String(messageId);
        });
    }

    function formatMessageTime(value) {
        const date = value ? new Date(value) : new Date();

        if (Number.isNaN(date.getTime())) {
            return "";
        }

        return date.toLocaleString("en-GB", {
            day: "2-digit",
            month: "short",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false
        });
    }

    // ==========================================
    // CONVERSATION SIDEBAR
    // ==========================================
    function formatSidebarTime(value) {
        const date = value ? new Date(value) : new Date();

        if (Number.isNaN(date.getTime())) {
            return "";
        }

        return date.toLocaleTimeString("en-GB", {
            hour: "2-digit",
            minute: "2-digit",
            hour12: false
        });
    }

    function getMessagePreview(message) {
        const mediaLabels = {
            photo: "📷 Photo",
            video: "🎥 Video",
            animation: "🎞 GIF",
            audio: "🎵 Audio",
            voice: "🎤 Voice message",
            video_note: "📹 Video message",
            sticker: "😊 Sticker",
            document: "📎 Document"
        };

        const mediaType = message.media_type || "text";
        const text = (message.text || "").trim();

        if (mediaType !== "text") {
            return mediaLabels[mediaType] ||
                (text || "📎 Media attachment");
        }

        return text || "New message";
    }

    function updateConversationSidebar(message) {
        if (!conversationList || !message) {
            return;
        }

        const chatIdValue = String(message.chat_id ?? "");

        if (!chatIdValue) {
            return;
        }

        let item = Array.from(
            conversationList.querySelectorAll(
                ".chat-conversation-item"
            )
        ).find(element => {
            return element.dataset.chatId === chatIdValue;
        });

        // Create a sidebar entry if this is a new conversation.
        if (!item) {
            const template = conversationList.dataset.chatUrlTemplate;

            if (!template) {
                console.warn(
                    "Missing data-chat-url-template on conversation list."
                );
                return;
            }

            const displayName =
                message.display_name ||
                message.first_name ||
                (message.username
                    ? `@${message.username}`
                    : chatIdValue);

            item = document.createElement("a");
            item.className = "chat-conversation-item";
            item.dataset.chatId = chatIdValue;
            item.dataset.displayName = displayName;
            item.dataset.username = message.username || "";

            // Replace the placeholder 0 with the actual chat ID.
            item.href = template.replace(
                /\/0\/?$/,
                `/${encodeURIComponent(chatIdValue)}/`
            );

            const avatar = document.createElement("div");
            avatar.className = "chat-conversation-avatar";
            avatar.textContent = displayName.charAt(0).toUpperCase();

            const info = document.createElement("div");
            info.className = "chat-conversation-info";

            const name = document.createElement("strong");
            name.className = "sidebar-name";
            name.textContent = displayName;

            const preview = document.createElement("p");
            preview.className = "sidebar-preview";

            const time = document.createElement("small");
            time.className = "sidebar-time";

            info.append(name, preview, time);
            item.append(avatar, info);

            const empty = conversationList.querySelector(
                "#chat-no-conversations"
            );

            if (empty) {
                empty.remove();
            }
        }

        // Update the latest message preview.
        const preview = item.querySelector(".sidebar-preview");
        const time = item.querySelector(".sidebar-time");

        if (preview) {
            const prefix =
                message.direction === "outgoing" ? "You: " : "";

            preview.textContent =
                prefix + getMessagePreview(message);
        }

        if (time) {
            time.textContent = formatSidebarTime(message.created_at);
        }

        // Move the recently active conversation to the top.
        conversationList.prepend(item);

        // Keep the currently open conversation highlighted.
        conversationList.querySelectorAll(
            ".chat-conversation-item"
        ).forEach(element => {
            element.classList.toggle(
                "selected",
                element.dataset.chatId === chatIdValue
            );
        });
    }

    // ==========================================
    // ADD MESSAGE TO CHAT
    // ==========================================
    function addMessage(message) {
        if (!message) {
            return;
        }

        // Only display messages belonging to this chat.
        if (
            message.chat_id !== undefined &&
            String(message.chat_id) !== chatId
        ) {
            return;
        }

        // Prevent duplicates from HTTP and WebSocket.
        if (messageExists(message.id)) {
            return;
        }

        const hasText = Boolean(message.text);
        const hasMedia = Boolean(message.media_url);

        if (!hasText && !hasMedia) {
            return;
        }

        const emptyState = history.querySelector(".empty-state");

        if (emptyState) {
            emptyState.remove();
        }

        const outgoing = message.direction === "outgoing";

        const bubble = document.createElement("div");
        bubble.className =
            "message-bubble " +
            (outgoing
                ? "message-bubble--outgoing"
                : "message-bubble--incoming");

        if (message.id !== undefined && message.id !== null) {
            bubble.dataset.messageId = String(message.id);
        }

        const sender = document.createElement("strong");
        sender.className = "message-sender";
        sender.textContent = outgoing
            ? "You"
            : (
                message.display_name ||
                message.first_name ||
                "Telegram user"
            );

        bubble.appendChild(sender);

        // Render message text or caption.
        if (hasText) {
            const body = document.createElement("p");
            body.className = "message-content";
            body.textContent = message.text;
            bubble.appendChild(body);
        }

        // Render attached media.
        if (hasMedia) {
            const media = document.createElement("div");
            media.className = "message-media";

            const url = message.media_url;
            const type = message.media_type || "document";

            if (["photo", "sticker"].includes(type)) {
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
                video.src = url;

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
        timestamp.textContent = formatMessageTime(message.created_at);

        bubble.appendChild(timestamp);
        history.appendChild(bubble);

        scrollToBottom();
    }

    // ==========================================
    // CSRF TOKEN
    // ==========================================
    function getCsrfToken() {
        if (csrfInput) {
            return csrfInput.value;
        }

        const csrfCookie = document.cookie
            .split("; ")
            .find(cookie => cookie.startsWith("csrftoken="));

        return csrfCookie
            ? decodeURIComponent(
                csrfCookie.substring("csrftoken=".length)
            )
            : "";
    }

    // ==========================================
    // WEBSOCKET CONNECTION
    // ==========================================
    function connectWebSocket() {
        if (manuallyClosed) {
            return;
        }

        const protocol =
            window.location.protocol === "https:"
                ? "wss:"
                : "ws:";

        socket = new WebSocket(
            `${protocol}//${window.location.host}/ws/telegram/`
        );

        socket.onopen = () => {
            setConnectionStatus("Connected", "#22c55e");
        };

        socket.onmessage = event => {
            try {
                const message = JSON.parse(event.data);

                // Update the current chat.
                addMessage(message);

                // Update the sidebar for every conversation.
                updateConversationSidebar(message);

            } catch (error) {
                console.error(
                    "Could not process WebSocket message:",
                    error
                );
            }
        };

        socket.onerror = error => {
            console.error("WebSocket error:", error);
            setConnectionStatus("Connection error", "#ef4444");
        };

        socket.onclose = event => {
            if (event.code === 4401) {
                setConnectionStatus(
                    "Please log in again",
                    "#ef4444"
                );
                return;
            }

            setConnectionStatus("Reconnecting...", "#f0ad4e");

            if (!manuallyClosed) {
                clearTimeout(reconnectTimer);
                reconnectTimer = setTimeout(
                    connectWebSocket,
                    3000
                );
            }
        };
    }

    // ==========================================
    // SELECTED FILE
    // ==========================================
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

    // ==========================================
    // SEND TEXT OR MEDIA
    // ==========================================
    form.addEventListener("submit", async event => {
        event.preventDefault();

        const text = input.value.trim();
        const file = fileInput?.files?.[0];

        if (!text && !file) {
            return;
        }

        if (text.length > 4096) {
            if (status) {
                status.textContent =
                    "Message must be 4096 characters or fewer.";
            }
            return;
        }

        if (file && file.size > 20 * 1024 * 1024) {
            if (status) {
                status.textContent =
                    "File size must not exceed 20 MB.";
            }
            return;
        }

        button.disabled = true;
        input.disabled = true;

        if (status) {
            status.textContent = file
                ? "Uploading media..."
                : "Sending...";
        }

        try {
            const csrfToken = getCsrfToken();
            let response;

            if (file) {
                if (!mediaUrl) {
                    throw new Error(
                        "Media upload URL is missing from the form."
                    );
                }

                const data = new FormData();
                data.append("file", file);
                data.append("caption", text);

                response = await fetch(mediaUrl, {
                    method: "POST",
                    headers: {
                        "X-CSRFToken": csrfToken
                    },
                    credentials: "same-origin",
                    body: data
                });

            } else {
                if (!sendUrl) {
                    throw new Error(
                        "Message send URL is missing from the form."
                    );
                }

                response = await fetch(sendUrl, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrfToken
                    },
                    credentials: "same-origin",
                    body: JSON.stringify({ text })
                });
            }

            const result = await response.json();

            if (
                !response.ok ||
                !(result.success === true || result.ok === true)
            ) {
                throw new Error(
                    result.error || "Message could not be sent."
                );
            }

            if (result.message) {
                const sentMessage = {
                    ...result.message,
                    chat_id: result.message.chat_id ?? chatId,
                    direction:
                        result.message.direction || "outgoing"
                };

                // These functions prevent duplicate chat bubbles
                // and keep the conversation list up to date.
                addMessage(sentMessage);
                updateConversationSidebar(sentMessage);
            }

            input.value = "";

            if (fileInput) {
                fileInput.value = "";
            }

            if (selectedFileLabel) {
                selectedFileLabel.textContent = "";
            }

            if (status) {
                status.textContent = file
                    ? "Media sent successfully."
                    : "Message sent.";
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
        }
    });

    // Support Enter-to-send if the input is changed to a textarea.
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

    // ==========================================
    // INITIALIZE
    // ==========================================
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
