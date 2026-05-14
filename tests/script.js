const chatForm = document.getElementById("chat-form");
const userInput = document.getElementById("user-input");
const chatBox = document.getElementById("chat-box");

chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const userMessage = userInput.value.trim();
    if (!userMessage) return;

    appendMessage("user", userMessage);
    userInput.value = "";

    appendMessage("assistant", ""); // Placeholder para resposta

    const lastMessage = chatBox.querySelector(".assistant:last-child");

    try {
        const response = await fetch("http://localhost:11434/api/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                model: "llama3",
                prompt: userMessage,
                stream: true
            })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let fullResponse = "";

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split("\n").filter(Boolean);

            for (const line of lines) {
                try {
                    const json = JSON.parse(line);
                    fullResponse += json.response;
                    lastMessage.textContent = fullResponse;
                    chatBox.scrollTop = chatBox.scrollHeight;
                } catch (err) {
                    // JSON incompleto, ignora
                    continue;
                }
            }
        }

    } catch (err) {
        lastMessage.textContent = "❌ Erro ao obter resposta.";
    }
});

function appendMessage(sender, text) {
    const div = document.createElement("div");
    div.classList.add("message", sender);
    div.textContent = text;
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
}
