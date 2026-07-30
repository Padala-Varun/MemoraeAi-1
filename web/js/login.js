/**
 * MemoraeAI — Login Page Logic
 * Neural network background animation + login form handling.
 */

document.addEventListener('DOMContentLoaded', () => {
    // If already logged in, redirect to chat
    AppState.load();
    if (AppState.isLoggedIn()) {
        window.location.href = 'chat.html';
        return;
    }

    initNeuralBackground();
    initLoginForm();
});

// ── Neural Network Canvas Background ──
function initNeuralBackground() {
    const canvas = document.getElementById('neural-canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let particles = [];
    let animationId;

    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }

    class Particle {
        constructor() {
            this.x = Math.random() * canvas.width;
            this.y = Math.random() * canvas.height;
            this.vx = (Math.random() - 0.5) * 0.4;
            this.vy = (Math.random() - 0.5) * 0.4;
            this.radius = Math.random() * 2 + 0.5;
            this.opacity = Math.random() * 0.5 + 0.1;
        }

        update() {
            this.x += this.vx;
            this.y += this.vy;

            if (this.x < 0 || this.x > canvas.width) this.vx *= -1;
            if (this.y < 0 || this.y > canvas.height) this.vy *= -1;
        }

        draw() {
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(99, 102, 241, ${this.opacity})`;
            ctx.fill();
        }
    }

    function init() {
        resize();
        const count = Math.min(Math.floor((canvas.width * canvas.height) / 12000), 100);
        particles = Array.from({ length: count }, () => new Particle());
    }

    function drawConnections() {
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);

                if (dist < 150) {
                    const opacity = (1 - dist / 150) * 0.15;
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = `rgba(99, 102, 241, ${opacity})`;
                    ctx.lineWidth = 0.5;
                    ctx.stroke();
                }
            }
        }
    }

    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        particles.forEach(p => {
            p.update();
            p.draw();
        });
        drawConnections();
        animationId = requestAnimationFrame(animate);
    }

    window.addEventListener('resize', () => {
        resize();
        const count = Math.min(Math.floor((canvas.width * canvas.height) / 12000), 100);
        while (particles.length < count) particles.push(new Particle());
        while (particles.length > count) particles.pop();
    });

    init();
    animate();
}

// ── Login Form ──
function initLoginForm() {
    const form = document.getElementById('login-form');
    const input = document.getElementById('username-input');
    const btn = document.getElementById('login-btn');
    const errorEl = document.getElementById('login-error');

    if (!form) return;

    // Auto-focus
    input.focus();

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = input.value.trim();

        if (!username) {
            showError('Please enter a username.');
            return;
        }

        if (username.length < 2) {
            showError('Username must be at least 2 characters.');
            return;
        }

        // Loading state
        btn.classList.add('loading');
        btn.disabled = true;
        hideError();

        try {
            const result = await api.login(username);
            AppState.login(result.user_id, result.username);
            Toast.success(`Welcome, ${result.username}!`);

            // Brief delay for toast visibility
            setTimeout(() => {
                window.location.href = 'chat.html';
            }, 500);
        } catch (error) {
            showError(error.message);
            btn.classList.remove('loading');
            btn.disabled = false;
        }
    });

    function showError(msg) {
        errorEl.textContent = msg;
        errorEl.classList.add('visible');
    }

    function hideError() {
        errorEl.classList.remove('visible');
    }
}
