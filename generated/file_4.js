/**
 * Password Strength Module
 * Calculates and displays password strength with comprehensive checks
 */

// Common passwords list (in a real app, this would be more comprehensive)
const COMMON_PASSWORDS = [
    'password', '123456', '12345678', '1234', 'qwerty',
    'letmein', 'welcome', 'admin', 'password1', '123456789'
];

/**
 * Calculates password strength score (0-1)
 * @param {string} password - Password to evaluate
 * @returns {number} - Strength score between 0 and 1
 */
function calculatePasswordStrength(password) {
    if (!password) return 0;

    let score = 0;
    const length = password.length;

    // Length score (0-0.3)
    score += Math.min(length / 30, 0.3);

    // Character variety score (0-0.5)
    const hasLower = /[a-z]/.test(password);
    const hasUpper = /[A-Z]/.test(password);
    const hasNumber = /[0-9]/.test(password);
    const hasSpecial = /[^a-zA-Z0-9]/.test(password);

    const varietyCount = [hasLower, hasUpper, hasNumber, hasSpecial].filter(Boolean).length;
    score += varietyCount * 0.125; // 0.5 max

    // Sequential characters penalty
    let sequentialCount = 0;
    for (let i = 0; i < password.length - 2; i++) {
        const charCode = password.charCodeAt(i);
        const nextCharCode = password.charCodeAt(i + 1);
        const nextNextCharCode = password.charCodeAt(i + 2);

        if (Math.abs(charCode - nextCharCode) === 1 && Math.abs(nextCharCode - nextNextCharCode) === 1) {
            sequentialCount++;
        }
    }

    score -= Math.min(sequentialCount * 0.05, 0.2);

    // Common password penalty
    if (COMMON_PASSWORDS.includes(password.toLowerCase())) {
        score = Math.max(0, score - 0.3);
    }

    // Ensure score is between 0 and 1
    return Math.max(0, Math.min(1, score));
}

/**
 * Updates the password strength indicator UI
 * @param {HTMLElement} strengthBar - The strength bar element
 * @param {number} strength - Strength score (0-1)
 */
function updatePasswordStrengthIndicator(strengthBar, strength) {
    if (!strengthBar) return;

    strengthBar.style.width = `${strength * 100}%`;

    // Change color based on strength
    if (strength < 0.3) {
        strengthBar.style.background = 'var(--error-color)';
    } else if (strength < 0.6) {
        strengthBar.style.background = 'var(--warning-color)';
    } else {
        strengthBar.style.background = 'var(--success-color)';
    }
}

// Export functions for other modules
window.calculatePasswordStrength = calculatePasswordStrength;
window.updatePasswordStrengthIndicator = updatePasswordStrengthIndicator;