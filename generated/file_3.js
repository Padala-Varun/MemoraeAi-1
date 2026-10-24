/**
 * Authentication Forms Module
 * Handles unified login/signup form functionality
 */

// Current authentication mode ('login', 'signup', or 'forgot')
let currentAuthMode = 'login';

// Common passwords list (in a real app, this would be more comprehensive)
const COMMON_PASSWORDS = [
    'password', '123456', '12345678', '1234', 'qwerty',
    'letmein', 'welcome', 'admin', 'password1', '123456789'
];

/**
 * Initializes the authentication form
 */
function initAuthForm() {
    // Get DOM elements
    const loginForm = document.getElementById('login-form');
    const signupForm = document.getElementById('signup-form');
    const forgotForm = document.getElementById('forgot-password-form');
    const loginModeBtn = document.getElementById('login-mode-btn');
    const signupModeBtn = document.getElementById('signup-mode-btn');
    const forgotLink = document.getElementById('forgot-password-link');
    const backToLoginLink = document.getElementById('back-to-login-link');
    const passwordInput = document.getElementById('signup-password');
    const strengthBar = document.getElementById('password-strength-bar');

    if (!loginForm || !signupForm || !forgotForm || !loginModeBtn || !signupModeBtn) return;

    // Set up mode toggle buttons
    loginModeBtn.addEventListener('click', () => switchAuthMode('login'));
    signupModeBtn.addEventListener('click', () => switchAuthMode('signup'));

    // Set up forgot password link
    forgotLink.addEventListener('click', (e) => {
        e.preventDefault();
        switchAuthMode('forgot');
    });

    // Set up back to login link
    backToLoginLink.addEventListener('click', (e) => {
        e.preventDefault();
        switchAuthMode('login');
    });

    // Initialize login form
    loginForm.addEventListener('submit', handleLoginSubmit);

    // Initialize signup form
    signupForm.addEventListener('submit', handleSignupSubmit);

    // Initialize forgot password form
    forgotForm.addEventListener('submit', handleForgotPasswordSubmit);

    // Password strength indicator
    if (passwordInput) {
        passwordInput.addEventListener('input', () => {
            const strength = calculatePasswordStrength(passwordInput.value);
            updatePasswordStrengthIndicator(strengthBar, strength);
            updatePasswordRequirements(passwordInput.value);
        });
    }

    // Auto-focus first input
    document.getElementById('username-input').focus();
}

/**
 * Switches between login, signup, and forgot password modes
 * @param {string} mode - 'login', 'signup', or 'forgot'
 */
function switchAuthMode(mode) {
    if (currentAuthMode === mode) return;

    const loginForm = document.getElementById('login-form');
    const signupForm = document.getElementById('signup-form');
    const forgotForm = document.getElementById('forgot-password-form');
    const loginModeBtn = document.getElementById('login-mode-btn');
    const signupModeBtn = document.getElementById('signup-mode-btn');

    // Update UI
    if (mode === 'login') {
        loginForm.classList.remove('hidden');
        signupForm.classList.add('hidden');
        forgotForm.classList.add('hidden');
        loginModeBtn.classList.add('active');
        signupModeBtn.classList.remove('active');
        document.getElementById('username-input').focus();
    } else if (mode === 'signup') {
        loginForm.classList.add('hidden');
        signupForm.classList.remove('hidden');
        forgotForm.classList.add('hidden');
        loginModeBtn.classList.remove('active');
        signupModeBtn.classList.add('active');
        document.getElementById('signup-username').focus();
    } else if (mode === 'forgot') {
        loginForm.classList.add('hidden');
        signupForm.classList.add('hidden');
        forgotForm.classList.remove('hidden');
        loginModeBtn.classList.remove('active');
        signupModeBtn.classList.remove('active');
        document.getElementById('forgot-email').focus();
    }

    // Reset forms
    loginForm.reset();
    signupForm.reset();
    forgotForm.reset();
    hideError('login-error');
    hideError('signup-error');
    hideError('forgot-error');

    currentAuthMode = mode;
}

/**
 * Handles login form submission
 * @param {Event} e - Form submit event
 */
async function handleLoginSubmit(e) {
    e.preventDefault();

    const form = e.target;
    const usernameInput = document.getElementById('username-input');
    const passwordInput = document.getElementById('password-input');
    const btn = document.getElementById('login-btn');
    const errorEl = document.getElementById('login-error');

    const username = usernameInput.value.trim();
    const password = passwordInput.value;

    // Validation
    if (!username) {
        showError('login-error', 'Please enter a username or email.');
        return;
    }

    if (!password) {
        showError('login-error', 'Please enter your password.');
        return;
    }

    // Loading state
    btn.classList.add('loading');
    btn.disabled = true;
    hideError('login-error');

    try {
        const result = await api.login(username, password);
        AppState.login(result.user_id, result.username);
        Toast.success(`Welcome back, ${result.username}!`);

        // Brief delay for toast visibility
        setTimeout(() => {
            window.location.href = 'chat.html';
        }, 500);
    } catch (error) {
        showError('login-error', error.message || 'Login failed. Please check your credentials and try again.');
        btn.classList.remove('loading');
        btn.disabled = false;
    }
}

/**
 * Handles signup form submission
 * @param {Event} e - Form submit event
 */
async function handleSignupSubmit(e) {
    e.preventDefault();

    const form = e.target;
    const usernameInput = document.getElementById('signup-username');
    const emailInput = document.getElementById('signup-email');
    const passwordInput = document.getElementById('signup-password');
    const confirmPasswordInput = document.getElementById('confirm-password');
    const btn = document.getElementById('signup-btn');
    const errorEl = document.getElementById('signup-error');

    const username = usernameInput.value.trim();
    const email = emailInput.value.trim();
    const password = passwordInput.value;
    const confirmPassword = confirmPasswordInput.value;

    // Validation
    if (!username) {
        showError('signup-error', 'Please enter a username.');
        return;
    }

    if (username.length < 2) {
        showError('signup-error', 'Username must be at least 2 characters.');
        return;
    }

    if (!validateUsername(username)) {
        showError('signup-error', 'Username can only contain letters, numbers, and underscores.');
        return;
    }

    if (!email) {
        showError('signup-error', 'Please enter your email address.');
        return;
    }

    if (!validateEmail(email)) {
        showError('signup-error', 'Please enter a valid email address.');
        return;
    }

    if (!password) {
        showError('signup-error', 'Please create a password.');
        return;
    }

    const passwordValidation = validatePassword(password);
    if (!passwordValidation.isValid) {
        showError('signup-error', passwordValidation.message);
        return;
    }

    if (password !== confirmPassword) {
        showError('signup-error', 'Passwords do not match.');
        return;
    }

    // Loading state
    btn.classList.add('loading');
    btn.disabled = true;
    hideError('signup-error');

    try {
        const result = await api.signup({
            username,
            email,
            password
        });

        // Auto-login after successful signup
        AppState.login(result.user_id, result.username);
        Toast.success(`Account created! Welcome, ${result.username}!`);

        // Brief delay for toast visibility
        setTimeout(() => {
            window.location.href = 'chat.html';
        }, 500);
    } catch (error) {
        showError('signup-error', error.message || 'Signup failed. Please try again.');
        btn.classList.remove('loading');
        btn.disabled = false;
    }
}

/**
 * Handles forgot password form submission
 * @param {Event} e - Form submit event
 */
async function handleForgotPasswordSubmit(e) {
    e.preventDefault();

    const form = e.target;
    const emailInput = document.getElementById('forgot-email');
    const btn = document.getElementById('forgot-btn');
    const errorEl = document.getElementById('forgot-error');

    const email = emailInput.value.trim();

    // Validation
    if (!email) {
        showError('forgot-error', 'Please enter your email address.');
        return;
    }

    if (!validateEmail(email)) {
        showError('forgot-error', 'Please enter a valid email address.');
        return;
    }

    // Loading state
    btn.classList.add('loading');
    btn.disabled = true;
    hideError('forgot-error');

    try {
        await api.forgotPassword(email);
        Toast.success('Password reset link sent! Check your email.');
        switchAuthMode('login');
    } catch (error) {
        showError('forgot-error', error.message || 'Failed to send reset link. Please try again.');
        btn.classList.remove('loading');
        btn.disabled = false;
    }
}

/**
 * Validates an email address
 * @param {string} email - Email address to validate
 * @returns {boolean} - True if valid, false otherwise
 */
function validateEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

/**
 * Validates a username
 * @param {string} username - Username to validate
 * @returns {boolean} - True if valid, false otherwise
 */
function validateUsername(username) {
    const re = /^[a-zA-Z0-9_]+$/;
    return re.test(username);
}

/**
 * Validates a password
 * @param {string} password - Password to validate
 * @returns {object} - Validation result with isValid and message properties
 */
function validatePassword(password) {
    if (password.length < 12) {
        return {
            isValid: false,
            message: 'Password must be at least 12 characters long.'
        };
    }

    if (!/[A-Z]/.test(password)) {
        return {
            isValid: false,
            message: 'Password must contain at least one uppercase letter.'
        };
    }

    if (!/[a-z]/.test(password)) {
        return {
            isValid: false,
            message: 'Password must contain at least one lowercase letter.'
        };
    }

    if (!/[0-9]/.test(password)) {
        return {
            isValid: false,
            message: 'Password must contain at least one number.'
        };
    }

    if (!/[^a-zA-Z0-9]/.test(password)) {
        return {
            isValid: false,
            message: 'Password must contain at least one special character.'
        };
    }

    if (COMMON_PASSWORDS.includes(password.toLowerCase())) {
        return {
            isValid: false,
            message: 'Password is too common. Please choose a more secure password.'
        };
    }

    return {
        isValid: true,
        message: 'Password is strong.'
    };
}

/**
 * Updates password requirements UI
 * @param {string} password - Current password value
 */
function updatePasswordRequirements(password) {
    const reqLength = document.getElementById('req-length');
    const reqUppercase = document.getElementById('req-uppercase');
    const reqLowercase = document.getElementById('req-lowercase');
    const reqNumber = document.getElementById('req-number');
    const reqSpecial = document.getElementById('req-special');
    const reqCommon = document.getElementById('req-common');

    // Length requirement
    if (password.length >= 12) {
        reqLength.classList.add('valid');
        reqLength.classList.remove('invalid');
    } else {
        reqLength.classList.add('invalid');
        reqLength.classList.remove('valid');
    }

    // Uppercase requirement
    if (/[A-Z]/.test(password)) {
        reqUppercase.classList.add('valid');
        reqUppercase.classList.remove('invalid');
    } else {
        reqUppercase.classList.add('invalid');
        reqUppercase.classList.remove('valid');
    }

    // Lowercase requirement
    if (/[a-z]/.test(password)) {
        reqLowercase.classList.add('valid');
        reqLowercase.classList.remove('invalid');
    } else {
        reqLowercase.classList.add('invalid');
        reqLowercase.classList.remove('valid');
    }

    // Number requirement
    if (/[0-9]/.test(password)) {
        reqNumber.classList.add('valid');
        reqNumber.classList.remove('invalid');
    } else {
        reqNumber.classList.add('invalid');
        reqNumber.classList.remove('valid');
    }

    // Special character requirement
    if (/[^a-zA-Z0-9]/.test(password)) {
        reqSpecial.classList.add('valid');
        reqSpecial.classList.remove('invalid');
    } else {
        reqSpecial.classList.add('invalid');
        reqSpecial.classList.remove('valid');
    }

    // Common password check
    if (password.length > 0 && !COMMON_PASSWORDS.includes(password.toLowerCase())) {
        reqCommon.classList.add('valid');
        reqCommon.classList.remove('invalid');
    } else {
        reqCommon.classList.add('invalid');
        reqCommon.classList.remove('valid');
    }
}

// Export functions for other modules
window.initAuthForm = initAuthForm;
window.switchAuthMode = switchAuthMode;