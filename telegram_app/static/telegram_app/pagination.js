
document.addEventListener("DOMContentLoaded", () => {
    const messageList = document.getElementById("message-list");
    const pagination = document.getElementById("message-pagination");
    const paginationInfo = document.getElementById("pagination-info");
    const pageIndicator = document.getElementById("page-indicator");
    const previousButton = document.getElementById("prev-page");
    const nextButton = document.getElementById("next-page");

    if (
        !messageList ||
        !pagination ||
        !paginationInfo ||
        !pageIndicator ||
        !previousButton ||
        !nextButton
    ) {
        return;
    }

    const pageSize = 5;
    let currentPage = 1;
    let previousCardCount = 0;

    function getCards() {
        return Array.from(messageList.children).filter(
            (element) => element.classList.contains("message-card")
        );
    }

    function renderPagination() {
        const cards = getCards();
        const total = cards.length;
        const totalPages = Math.max(1, Math.ceil(total / pageSize));

        currentPage = Math.min(currentPage, totalPages);

        const startIndex = (currentPage - 1) * pageSize;
        const endIndex = Math.min(startIndex + pageSize, total);

        cards.forEach((card, index) => {
            card.hidden = index < startIndex || index >= endIndex;
        });

        paginationInfo.textContent = total
            ? `Showing ${startIndex + 1}–${endIndex} of ${total} messages`
            : "Showing 0 messages";

        pageIndicator.textContent =
            `Page ${currentPage} of ${totalPages}`;

        previousButton.disabled = currentPage <= 1;
        nextButton.disabled = currentPage >= totalPages;

        pagination.hidden = total === 0;

        const emptyState = document.getElementById("empty-state");

        if (emptyState) {
            emptyState.hidden = total > 0;
        }

        previousCardCount = total;
    }

    previousButton.addEventListener("click", () => {
        if (currentPage > 1) {
            currentPage--;
            renderPagination();
        }
    });

    nextButton.addEventListener("click", () => {
        const totalPages = Math.max(
            1,
            Math.ceil(getCards().length / pageSize)
        );

        if (currentPage < totalPages) {
            currentPage++;
            renderPagination();
        }
    });

    const observer = new MutationObserver(() => {
        const currentCount = getCards().length;

        // Reset to the first page when the message list is replaced
        // or cleared. Keep the current page for ordinary additions.
        if (currentCount < previousCardCount) {
            currentPage = 1;
        }

        renderPagination();
    });

    observer.observe(messageList, {
        childList: true
    });

    renderPagination();
});
