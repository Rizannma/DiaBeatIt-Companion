// Login form validation and enhancement
document.addEventListener('DOMContentLoaded', function() {
    const loginForm = document.getElementById('loginForm');
    const loginBtn = document.getElementById('loginBtn');
    const emailInput = document.getElementById('email');
    const passwordInput = document.getElementById('password');

    function validateEmail(email) {
        const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return re.test(email);
    }

    function showError(input, message) {
        const errorDiv = input.parentElement.parentElement.querySelector('.text-danger');
        if (errorDiv) {
            errorDiv.textContent = message;
        }
        input.classList.add('is-invalid');
    }

    function clearError(input) {
        const errorDiv = input.parentElement.parentElement.querySelector('.text-danger');
        if (errorDiv) {
            errorDiv.textContent = '';
        }
        input.classList.remove('is-invalid');
    }

    // Real-time validation
    emailInput.addEventListener('blur', function() {
        if (this.value.trim() === '') {
            showError(this, 'Email is required.');
        } else if (!validateEmail(this.value)) {
            showError(this, 'Please enter a valid email address.');
        } else {
            clearError(this);
        }
    });

    passwordInput.addEventListener('blur', function() {
        if (this.value.trim() === '') {
            showError(this, 'Password is required.');
        } else {
            clearError(this);
        }
    });

    // Form submission
    loginForm.addEventListener('submit', function(e) {
        let isValid = true;

        // Validate email
        if (emailInput.value.trim() === '') {
            showError(emailInput, 'Email is required.');
            isValid = false;
        } else if (!validateEmail(emailInput.value)) {
            showError(emailInput, 'Please enter a valid email address.');
            isValid = false;
        }

        // Validate password
        if (passwordInput.value.trim() === '') {
            showError(passwordInput, 'Password is required.');
            isValid = false;
        }

        if (!isValid) {
            e.preventDefault();
            return false;
        }

        // Show loading state
        loginBtn.disabled = true;
        loginBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Signing In...';
    });

    // Clear errors on input
    [emailInput, passwordInput].forEach(input => {
        input.addEventListener('input', function() {
            if (this.classList.contains('is-invalid')) {
                clearError(this);
            }
        });
    });

    // Auto-focus email field
    emailInput.focus();

    // Password visibility toggle
    const passwordToggle = document.getElementById('passwordToggle');
    passwordToggle.addEventListener('click', function(e) {
        e.preventDefault();
        const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
        passwordInput.setAttribute('type', type);
        
        // Toggle icon
        const icon = this.querySelector('i');
        if (type === 'password') {
            icon.classList.remove('bi-eye-slash');
            icon.classList.add('bi-eye');
        } else {
            icon.classList.remove('bi-eye');
            icon.classList.add('bi-eye-slash');
        }
    });
});

