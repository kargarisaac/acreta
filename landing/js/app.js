/**
 * Acreta Landing Page - Interactive Features
 * Neural constellation animations and interactions
 */

// ========================================
// Neural Network Background Animation
// ========================================
class NeuralNetwork {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.nodes = [];
    this.connections = [];
    this.mouse = { x: null, y: null };
    this.animationId = null;
    
    this.config = {
      nodeCount: 60,
      connectionDistance: 150,
      mouseDistance: 200,
      nodeSpeed: 0.3,
      nodeRadius: { min: 1, max: 3 },
      colors: {
        node: 'rgba(168, 85, 247, 0.6)',
        connection: 'rgba(0, 245, 212, 0.15)',
        mouse: 'rgba(0, 245, 212, 0.3)'
      }
    };
    
    this.init();
  }
  
  init() {
    this.resize();
    this.createNodes();
    this.bindEvents();
    this.animate();
  }
  
  resize() {
    this.canvas.width = window.innerWidth;
    this.canvas.height = window.innerHeight;
  }
  
  createNodes() {
    this.nodes = [];
    for (let i = 0; i < this.config.nodeCount; i++) {
      this.nodes.push({
        x: Math.random() * this.canvas.width,
        y: Math.random() * this.canvas.height,
        vx: (Math.random() - 0.5) * this.config.nodeSpeed,
        vy: (Math.random() - 0.5) * this.config.nodeSpeed,
        radius: Math.random() * (this.config.nodeRadius.max - this.config.nodeRadius.min) + this.config.nodeRadius.min,
        pulsePhase: Math.random() * Math.PI * 2
      });
    }
  }
  
  bindEvents() {
    window.addEventListener('resize', () => this.resize());
    
    window.addEventListener('mousemove', (e) => {
      this.mouse.x = e.clientX;
      this.mouse.y = e.clientY;
    });
    
    window.addEventListener('mouseleave', () => {
      this.mouse.x = null;
      this.mouse.y = null;
    });
  }
  
  updateNodes() {
    this.nodes.forEach(node => {
      // Update position
      node.x += node.vx;
      node.y += node.vy;
      
      // Bounce off edges
      if (node.x < 0 || node.x > this.canvas.width) node.vx *= -1;
      if (node.y < 0 || node.y > this.canvas.height) node.vy *= -1;
      
      // Keep in bounds
      node.x = Math.max(0, Math.min(this.canvas.width, node.x));
      node.y = Math.max(0, Math.min(this.canvas.height, node.y));
      
      // Mouse interaction
      if (this.mouse.x !== null && this.mouse.y !== null) {
        const dx = this.mouse.x - node.x;
        const dy = this.mouse.y - node.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        
        if (dist < this.config.mouseDistance) {
          const force = (this.config.mouseDistance - dist) / this.config.mouseDistance;
          node.vx += (dx / dist) * force * 0.02;
          node.vy += (dy / dist) * force * 0.02;
        }
      }
      
      // Limit velocity
      const speed = Math.sqrt(node.vx * node.vx + node.vy * node.vy);
      if (speed > this.config.nodeSpeed * 2) {
        node.vx = (node.vx / speed) * this.config.nodeSpeed * 2;
        node.vy = (node.vy / speed) * this.config.nodeSpeed * 2;
      }
      
      // Update pulse
      node.pulsePhase += 0.02;
    });
  }
  
  draw() {
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    
    // Draw connections
    this.ctx.strokeStyle = this.config.colors.connection;
    this.ctx.lineWidth = 1;
    
    for (let i = 0; i < this.nodes.length; i++) {
      for (let j = i + 1; j < this.nodes.length; j++) {
        const dx = this.nodes[i].x - this.nodes[j].x;
        const dy = this.nodes[i].y - this.nodes[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        
        if (dist < this.config.connectionDistance) {
          const opacity = (1 - dist / this.config.connectionDistance) * 0.5;
          this.ctx.strokeStyle = `rgba(0, 245, 212, ${opacity * 0.3})`;
          this.ctx.beginPath();
          this.ctx.moveTo(this.nodes[i].x, this.nodes[i].y);
          this.ctx.lineTo(this.nodes[j].x, this.nodes[j].y);
          this.ctx.stroke();
        }
      }
      
      // Mouse connections
      if (this.mouse.x !== null && this.mouse.y !== null) {
        const dx = this.mouse.x - this.nodes[i].x;
        const dy = this.mouse.y - this.nodes[i].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        
        if (dist < this.config.mouseDistance) {
          const opacity = (1 - dist / this.config.mouseDistance) * 0.5;
          this.ctx.strokeStyle = `rgba(0, 245, 212, ${opacity})`;
          this.ctx.beginPath();
          this.ctx.moveTo(this.mouse.x, this.mouse.y);
          this.ctx.lineTo(this.nodes[i].x, this.nodes[i].y);
          this.ctx.stroke();
        }
      }
    }
    
    // Draw nodes
    this.nodes.forEach(node => {
      const pulse = Math.sin(node.pulsePhase) * 0.3 + 0.7;
      const radius = node.radius * pulse;
      
      // Glow
      const gradient = this.ctx.createRadialGradient(
        node.x, node.y, 0,
        node.x, node.y, radius * 4
      );
      gradient.addColorStop(0, `rgba(168, 85, 247, ${0.4 * pulse})`);
      gradient.addColorStop(1, 'transparent');
      
      this.ctx.fillStyle = gradient;
      this.ctx.beginPath();
      this.ctx.arc(node.x, node.y, radius * 4, 0, Math.PI * 2);
      this.ctx.fill();
      
      // Core
      this.ctx.fillStyle = this.config.colors.node;
      this.ctx.beginPath();
      this.ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
      this.ctx.fill();
    });
  }
  
  animate() {
    this.updateNodes();
    this.draw();
    this.animationId = requestAnimationFrame(() => this.animate());
  }
  
  destroy() {
    if (this.animationId) {
      cancelAnimationFrame(this.animationId);
    }
  }
}

// ========================================
// Intersection Observer for Scroll Animations
// ========================================
class ScrollAnimations {
  constructor() {
    this.observerOptions = {
      threshold: 0.1,
      rootMargin: '0px 0px -50px 0px'
    };
    
    this.init();
  }
  
  init() {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('animate-in');
          observer.unobserve(entry.target);
        }
      });
    }, this.observerOptions);
    
    // Observe elements
    document.querySelectorAll('.step, .agent-node, .open-core-text, .code-preview').forEach(el => {
      el.style.opacity = '0';
      el.style.transform = 'translateY(30px)';
      el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
      observer.observe(el);
    });
  }
}

// Add CSS for animated elements
const style = document.createElement('style');
style.textContent = `
  .animate-in {
    opacity: 1 !important;
    transform: translateY(0) !important;
  }
`;
document.head.appendChild(style);

// ========================================
// Email Form Handling
// ========================================
class EmailForm {
  constructor() {
    this.form = document.querySelector('.signup-form');
    this.input = document.querySelector('.email-input');
    this.button = document.querySelector('.signup-btn');
    
    if (this.form && this.input && this.button) {
      this.init();
    }
  }
  
  init() {
    this.button.addEventListener('click', (e) => this.handleSubmit(e));
    this.input.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') this.handleSubmit(e);
    });
  }
  
  handleSubmit(e) {
    e.preventDefault();
    
    const email = this.input.value.trim();
    
    if (!this.validateEmail(email)) {
      this.showError('Please enter a valid email address');
      return;
    }
    
    // Simulate submission
    this.button.disabled = true;
    this.button.innerHTML = '<span>Subscribing...</span>';
    
    setTimeout(() => {
      this.showSuccess();
      this.input.value = '';
    }, 1500);
  }
  
  validateEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }
  
  showError(message) {
    this.input.style.borderColor = '#f87171';
    this.input.style.animation = 'shake 0.5s ease';
    
    setTimeout(() => {
      this.input.style.borderColor = '';
      this.input.style.animation = '';
    }, 2000);
    
    // Could add a toast notification here
    console.error(message);
  }
  
  showSuccess() {
    this.button.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M3 8L7 12L13 4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <span>You're on the list!</span>
    `;
    this.button.style.background = 'linear-gradient(135deg, #4ade80, #22c55e)';
    
    setTimeout(() => {
      this.button.disabled = false;
      this.button.innerHTML = `
        <span>Notify Me</span>
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M3 8H13M13 8L9 4M13 8L9 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      `;
      this.button.style.background = '';
    }, 3000);
  }
}

// Add shake animation
const shakeStyle = document.createElement('style');
shakeStyle.textContent = `
  @keyframes shake {
    0%, 100% { transform: translateX(0); }
    25% { transform: translateX(-5px); }
    75% { transform: translateX(5px); }
  }
`;
document.head.appendChild(shakeStyle);

// ========================================
// Smooth Scroll for Navigation
// ========================================
class SmoothScroll {
  constructor() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
      anchor.addEventListener('click', (e) => this.handleClick(e));
    });
  }
  
  handleClick(e) {
    e.preventDefault();
    const target = document.querySelector(e.currentTarget.getAttribute('href'));
    
    if (target) {
      const offset = 80; // Account for fixed nav
      const targetPosition = target.getBoundingClientRect().top + window.pageYOffset - offset;
      
      window.scrollTo({
        top: targetPosition,
        behavior: 'smooth'
      });
    }
  }
}

// ========================================
// Parallax Effect for Hero
// ========================================
class ParallaxEffect {
  constructor() {
    this.hero = document.querySelector('.hero-content');
    this.mascot = document.querySelector('.mascot-container');
    
    if (this.hero && !window.matchMedia('(pointer: coarse)').matches) {
      this.init();
    }
  }
  
  init() {
    let ticking = false;
    
    window.addEventListener('scroll', () => {
      if (!ticking) {
        requestAnimationFrame(() => {
          this.update();
          ticking = false;
        });
        ticking = true;
      }
    });
  }
  
  update() {
    const scrolled = window.pageYOffset;
    const rate = scrolled * 0.3;
    
    if (this.hero) {
      this.hero.style.transform = `translateY(${rate * 0.5}px)`;
      this.hero.style.opacity = 1 - (scrolled / 700);
    }
  }
}

// ========================================
// Initialize Everything
// ========================================
document.addEventListener('DOMContentLoaded', () => {
  // Neural network background
  const canvas = document.getElementById('neural-canvas');
  if (canvas) {
    new NeuralNetwork(canvas);
  }
  
  // Scroll animations
  new ScrollAnimations();
  
  // Email form
  new EmailForm();
  
  // Smooth scroll
  new SmoothScroll();
  
  // Parallax (desktop only)
  new ParallaxEffect();
  
  // Console easter egg
  console.log(
    '%c◉ Acreta',
    'font-size: 24px; font-weight: bold; color: #a855f7;'
  );
  console.log(
    '%cCross-platform agent learning layer',
    'font-size: 14px; color: #94a3b8;'
  );
  console.log(
    '%cYour agents never start from zero again.',
    'font-size: 12px; color: #00f5d4; font-style: italic;'
  );
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
  // Any cleanup needed
});
