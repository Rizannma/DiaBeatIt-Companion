
function initOtpBoxes() {
    const groups = document.querySelectorAll('.otp-inputs[data-target]');
    groups.forEach((group) => {
        const targetId = group.getAttribute('data-target');
        const hiddenInput = document.getElementById(targetId);
        const boxes = Array.from(group.querySelectorAll('.otp-digit'));
        if (!hiddenInput || boxes.length === 0) {
            return;
        }

        function syncHiddenValue() {
            hiddenInput.value = boxes.map((box) => box.value).join('');
        }

        function fillFromString(value) {
            const digits = (value || '').replace(/\D/g, '').slice(0, boxes.length).split('');
            boxes.forEach((box, idx) => {
                box.value = digits[idx] || '';
            });
            syncHiddenValue();
        }

        fillFromString(hiddenInput.value);

        boxes.forEach((box, index) => {
            box.addEventListener('input', () => {
                box.value = box.value.replace(/\D/g, '').slice(-1);
                if (box.value && index < boxes.length - 1) {
                    boxes[index + 1].focus();
                }
                syncHiddenValue();
            });

            box.addEventListener('keydown', (event) => {
                if (event.key === 'Backspace' && !box.value && index > 0) {
                    boxes[index - 1].focus();
                }
                if (event.key === 'ArrowLeft' && index > 0) {
                    event.preventDefault();
                    boxes[index - 1].focus();
                }
                if (event.key === 'ArrowRight' && index < boxes.length - 1) {
                    event.preventDefault();
                    boxes[index + 1].focus();
                }
            });

            box.addEventListener('paste', (event) => {
                event.preventDefault();
                fillFromString(event.clipboardData.getData('text'));
                const lastFilledIndex = boxes.findIndex((item) => !item.value);
                if (lastFilledIndex === -1) {
                    boxes[boxes.length - 1].focus();
                } else {
                    boxes[lastFilledIndex].focus();
                }
            });
        });
    });
}

initOtpBoxes();

const otpPage = document.getElementById('otpPage');
if (otpPage) {
    let countdown = Number(otpPage.dataset.remainingSeconds || 0);
    const countdownElement = document.getElementById('countdown');
    const otpMessage = document.getElementById('otpMessage');
    const verifyBtn = document.getElementById('verifyBtn');
    const expired = otpPage.dataset.expired === 'true';
    const resendSection = document.getElementById('resendSection');
    const otpExpirationText = document.getElementById('otpExpirationText');
    const resendUrl = otpPage.dataset.resendUrl;

    if (expired) {
        if (otpExpirationText) otpExpirationText.classList.add('d-none');
        if (otpMessage) otpMessage.classList.remove('d-none');
        if (verifyBtn) verifyBtn.disabled = true;
    }

    const timer = setInterval(() => {
        if (countdown <= 0) {
            clearInterval(timer);
            if (otpExpirationText) otpExpirationText.classList.add('d-none');
            if (verifyBtn) verifyBtn.disabled = true;
            if (!expired && resendSection && resendUrl) {
                resendSection.innerHTML = `<a href='${resendUrl}' class='text-danger fw-bold text-decoration-none'>Resend Code</a>`;
            }
            if (otpMessage) {
                otpMessage.textContent = 'OTP expired. Please request a new one.';
                otpMessage.classList.remove('d-none');
            }
            return;
        }
        countdown--;
        countdownElement.textContent = countdown;
    }, 1000);
}
