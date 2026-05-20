document.addEventListener('DOMContentLoaded', function() {
    const successAlert = document.querySelector('.alert-success');
    const signupForm = document.getElementById('signupForm');
    const accountType = document.getElementById('account_for');
    const selfSec = document.getElementById('self_section');
    const otherSec = document.getElementById('other_section');
    const consentBox = document.getElementById('consent');
    const previewBtn = document.getElementById('previewBtn');
    const passwordToggles = document.querySelectorAll('.password-toggle');
    const passwordInput = document.getElementById('password_input');
    const confirmInput = document.getElementById('confirm_password');
    const meter = document.getElementById('strength_meter');
    const text = document.getElementById('strength_text');

    const validators = {
        full_name: (val) => /^[a-zA-Z]+,\s[a-zA-Z\s]+$/.test(val) ? "" : "Use: Surname, First Name Middle Name",
        patient_name: (val) => /^[a-zA-Z]+,\s[a-zA-Z\s]+$/.test(val) ? "" : "Use: Surname, First Name Middle Name",
        email: (val) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val) ? "" : "Enter a valid email address.",
        age: (val) => val >= 18 ? "" : "Must be 18+ to register.",
        password_input: (val) => (val.length >= 8 && /[A-Z]/.test(val) && /[0-9]/.test(val) && /[^A-Za-z0-9]/.test(val))
            ? "" : "Weak password format.",
        confirm_password: (val) => val === passwordInput.value ? "" : "Passwords don't match."
    };

    function setRequiredState() {
        const patientFields = [
            document.getElementById('patient_name'),
            document.getElementById('patient_age'),
            document.getElementById('relationship')
        ];

        if (accountType.value === 'other') {
            otherSec.style.display = 'block';
            patientFields.forEach(field => {
                field.disabled = false;
            });
            consentBox.disabled = false;
        } else {
            otherSec.style.display = 'none';
            patientFields.forEach(field => {
                field.disabled = true;
                field.classList.remove('invalid-field');
            });
            consentBox.disabled = true;
            consentBox.checked = false;
        }
    }

    function setFieldError(input, message) {
        const errorSpan = document.getElementById(`error-${input.id}`);
        if (message) {
            input.classList.add('invalid-field');
            if (errorSpan) errorSpan.textContent = message;
        } else {
            input.classList.remove('invalid-field');
            if (errorSpan) errorSpan.textContent = '';
        }
    }

    function validateInput(input) {
        if (!input.checkValidity()) {
            if (input.validity.valueMissing) {
                setFieldError(input, 'This field is required.');
                return false;
            }
        }

        if (validators[input.id]) {
            const msg = validators[input.id](input.value);
            setFieldError(input, msg);
            return !msg;
        }

        if (input.type === 'checkbox' && input.required && !input.checked) {
            setFieldError(input, 'This field is required.');
            return false;
        }

        setFieldError(input, '');
        return true;
    }

    function validateAllFields() {
        let valid = true;
        const fields = signupForm.querySelectorAll('.form-control, .form-select, .form-check-input');
        fields.forEach(input => {
            if (input.disabled) return;
            if (!validateInput(input)) valid = false;
        });
        return valid;
    }

    accountType.addEventListener('change', setRequiredState);
    setRequiredState();

    signupForm.querySelectorAll('.form-control, .form-select, .form-check-input').forEach(input => {
        input.addEventListener('input', () => {
            if (input.disabled) return;
            validateInput(input);
        });
        input.addEventListener('invalid', function() {
            validateInput(input);
        });
    });

    passwordToggles.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.getAttribute('data-target');
            const targetInput = document.getElementById(targetId);
            if (!targetInput) return;
            if (targetInput.type === 'password') {
                targetInput.type = 'text';
                btn.innerHTML = '<i class="bi bi-eye-slash"></i>';
            } else {
                targetInput.type = 'password';
                btn.innerHTML = '<i class="bi bi-eye"></i>';
            }
        });
    });

    passwordInput.addEventListener('input', function() {
        const val = passwordInput.value;
        if (val.length < 5) {
            meter.style.width = '25%'; meter.style.backgroundColor = '#ef4444'; text.innerText = 'Weak';
        } else if (val.length < 8 || !/[!@#$%^&*]/.test(val)) {
            meter.style.width = '60%'; meter.style.backgroundColor = '#fbbf24'; text.innerText = 'Moderate';
        } else {
            meter.style.width = '100%'; meter.style.backgroundColor = '#10b981'; text.innerText = 'Strong';
        }
        validateInput(passwordInput);
        if (confirmInput.value) {
            validateInput(confirmInput);
        }
    });

    previewBtn.addEventListener('click', function() {
        if (!validateAllFields() || !signupForm.checkValidity()) {
            signupForm.reportValidity();
            return;
        }
        const accountFor = document.getElementById('account_for');
        const nameEl = document.getElementById('full_name');
        const emailEl = document.getElementById('email');
        const ageEl = document.getElementById('age');
        const patientNameEl = document.getElementById('patient_name');
        const patientAgeEl = document.getElementById('patient_age');
        const relationshipEl = document.getElementById('relationship');

        document.getElementById('preview-name').textContent = nameEl.value;
        document.getElementById('preview-email').textContent = emailEl.value;
        document.getElementById('preview-age').textContent = ageEl.value;
        document.getElementById('preview-account').textContent = accountFor.value === 'self' ? 'Myself' : 'Someone Else';

        if (accountFor.value === 'self') {
            document.getElementById('patient-info').style.display = 'none';
        } else {
            document.getElementById('patient-info').style.display = 'block';
            document.getElementById('preview-patient-name').textContent = patientNameEl.value;
            document.getElementById('preview-patient-age').textContent = patientAgeEl.value;
            document.getElementById('preview-relationship').textContent = relationshipEl.value;
        }

        const modal = new bootstrap.Modal(document.getElementById('previewModal'));
        modal.show();
    });

    document.getElementById('confirmSubmit').addEventListener('click', function() {
        signupForm.submit();
    });

    if (successAlert) {
        const successModal = new bootstrap.Modal(document.getElementById('successModal'));
        setTimeout(() => successModal.show(), 300);
        setTimeout(() => signupForm.reset(), 500);
    }
});

    document.getElementById('confirmSubmit').addEventListener('click', function() {
        document.getElementById('signupForm').submit();
    });

    document.getElementById('confirmSubmit').addEventListener('click', function() {
        const form = document.getElementById('signupForm');
        
        // Validate all fields one more time before submission
        const fields = form.querySelectorAll('.form-control, .form-select, .form-check-input');
        let isValid = true;
        
        fields.forEach(input => {
            if (input.disabled) return;
            // Check basic validity
            if (!input.checkValidity()) {
                isValid = false;
                return;
            }
        });
        
        if (!isValid) {
            console.warn('Form validation failed at submission');
            form.reportValidity();
            return;
        }
        
        // Close modal first
        const modal = bootstrap.Modal.getInstance(document.getElementById('previewModal'));
        if (modal) {
            modal.hide();
            document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
                backdrop.remove();
            });
            document.body.classList.remove('modal-open');
        }
        
        // Submit the form
        form.submit();
    });

    // Handle Edit Details button to properly close modal
    document.querySelectorAll('[data-bs-dismiss="modal"]').forEach(button => {
        button.addEventListener('click', function() {
            const modal = bootstrap.Modal.getInstance(document.getElementById('previewModal'));
            if (modal) {
                modal.hide();
                // Remove backdrop if it persists
                document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
                    backdrop.remove();
                });
                // Re-enable scrolling on body
                document.body.classList.remove('modal-open');
            }
        });
    });

    // Handle consent checkbox with Enter key
    const consentCheckbox = document.getElementById('consent');
    if (consentCheckbox) {
        consentCheckbox.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                this.checked = !this.checked;
                this.dispatchEvent(new Event('change'));
            }
        });
    }
