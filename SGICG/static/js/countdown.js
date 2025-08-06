document.addEventListener('DOMContentLoaded', function() {
    const countdownElements = document.querySelectorAll('.countdown');

    function updateCountdown() {
        countdownElements.forEach(el => {
            const deadline = el.dataset.deadline;
            if (!deadline) {
                el.innerHTML = '<span class="badge bg-secondary">N/A</span>';
                return;
            }

            const deadlineDate = new Date(deadline).getTime();
            const now = new Date().getTime();
            const distance = deadlineDate - now;

            if (distance < 0) {
                el.innerHTML = '<span class="badge bg-danger">Retrasado</span>';
                return;
            }

            const days = Math.floor(distance / (1000 * 60 * 60 * 24));
            const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
            const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
            const seconds = Math.floor((distance % (1000 * 60)) / 1000);

            let output = '';
            if (days > 0) output += `${days}d `;
            output += `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
            
            el.innerHTML = `<span class="badge bg-success">${output}</span>`;
        });
    }

    if (countdownElements.length > 0) {
        updateCountdown();
        setInterval(updateCountdown, 1000);
    }
});