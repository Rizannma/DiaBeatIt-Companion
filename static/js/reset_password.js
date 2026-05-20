
    const passwordInput = document.getElementById('password_input');
    const confirmInput = document.getElementById('confirm_password');

    const resetValidators = {
        password_input: (val) => (val.length >= 8 && /[A-Z]/.test(val) && /[0-9]/.test(val) && /[^A-Za-z0-9]/.test(val))
            ? '' : 'Minimum of 8 characters, mixed case, numbers, symbols',
        confirm_password: (val) => val === passwordInput.value ? '' : "Passwords don't match."
    };

    [passwordInput, confirmInput].forEach(input => {
        if (!input) return;
        input.addEventListener('input', () => {
            const errorSpan = document.getElementById(`error-${input.id}`);
            if (resetValidators[input.id] && errorSpan) {
                const msg = resetValidators[input.id](input.value);
                errorSpan.textContent = msg;
                input.style.border = msg ? '1px solid #dc3545' : 'none';
            }
            if (input.id === 'password_input' && confirmInput.value) {
                const confirmSpan = document.getElementById('error-confirm_password');
                const confirmMsg = resetValidators.confirm_password(confirmInput.value);
                confirmSpan.textContent = confirmMsg;
                confirmInput.style.border = confirmMsg ? '1px solid #dc3545' : 'none';
            }
        });
    });
