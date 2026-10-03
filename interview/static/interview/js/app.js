document.addEventListener('DOMContentLoaded', () => {
    const forms = document.querySelectorAll('form');

    forms.forEach((form) => {
        form.addEventListener('submit', (event) => {
            if (form.dataset.submitting === 'true') {
                event.preventDefault();
                return;
            }

            form.dataset.submitting = 'true';
            const button = event.submitter || form.querySelector('button[type="submit"]');

            if (button) {
                button.classList.add('disabled');
                button.setAttribute('aria-disabled', 'true');
                button.textContent = 'Submitting...';
            }
        });
    });
});
