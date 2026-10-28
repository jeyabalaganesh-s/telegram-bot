
document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("send-message-form");
    const input = document.getElementById("outgoing-message");
    const history = document.getElementById("chat-history");
    const status = document.getElementById("send-status");
    const button = document.getElementById("send-button");

    if (!form || !input || !history) return;

    const csrfInput = form.querySelector(
        'input[name="csrfmiddlewaretoken"]'
    );

    function addMessage(text, direction, timestamp) {
        const bubble = document.createElement("div");
        bubble.style.cssText =
            "padding:12px;margin:10px 0;border-radius:12px;" +
            "overflow-wrap:anywhere;" +
            (direction === "outgoing"
                ? "background:#eaf4ff;margin-left:15%;"
                : "background:#f1f5f9;margin-right:15%;");

        const sender = document.createElement("strong");
        sender.textContent = direction === "outgoing" ? "You" : "Telegram user";

        const body = document.createElement("p");
        body.textContent = text;
        body.style.cssText = "white-space:pre-wrap;margin-top:6px";

        const time = document.createElement("small");
        time.textContent = timestamp
            ? new Date(timestamp).toLocaleString()
            : new Date().toLocaleString();
        time.style.color = "#68758b";

        bubble.append(sender, body, time);
        history.appendChild(bubble);
        history.scrollTop = history.scrollHeight;
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();

        const text = input.value.trim();
        if (!text) return;

        button.disabled = true;
        status.textContent = "Sending...";

        try {
            const response = await fetch(form.dataset.sendUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfInput.value,
                },
                body: JSON.stringify({ text }),
                credentials: "same-origin",
            });

            const result = await response.json();

            if (!response.ok || !result.ok) {
                throw new Error(result.error || "Message could not be sent.");
            }

            addMessage(
                result.message.text,
                "outgoing",
                result.message.created_at
            );

            input.value = "";
            status.textContent = "Message sent.";
            input.focus();
        } catch (error) {
            status.textContent = error.message || "Something went wrong.";
        } finally {
            button.disabled = false;
        }
    });

    history.scrollTop = history.scrollHeight;
});
