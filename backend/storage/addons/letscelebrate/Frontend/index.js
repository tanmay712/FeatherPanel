(function () {
  // --- Default Fireworks Settings ---
  const DEFAULTS = {
    fireworkCount: 3,
    particleCount: 50,
    minSize: 2,
    maxSize: 6,
    minSpeed: 2,
    maxSpeed: 8,
    minOpacity: 0.6,
    maxOpacity: 1.0,
    colors: [
      "#ffd700",
      "#ff6b6b",
      "#4ecdc4",
      "#45b7d1",
      "#f7b731",
      "#ee5a6f",
      "#a55eea",
      "#ffffff",
    ],
    explosionRadius: 80,
    gravity: 0.1,
  };

  // --- State ---
  const STORAGE_KEY = "letscelebrate-settings";
  const STORAGE_STATE_KEY = "letscelebrate-state";

  // Load settings from localStorage
  function loadSettings() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        return { ...DEFAULTS, ...parsed };
      }
    } catch (e) {
      console.warn("Failed to load settings:", e);
    }
    return { ...DEFAULTS };
  }

  // Save settings to localStorage
  function saveSettings() {
    try {
      const toSave = {
        fireworkCount: settings.fireworkCount,
        particleCount: settings.particleCount,
        minSize: settings.minSize,
        maxSize: settings.maxSize,
        minSpeed: settings.minSpeed,
        maxSpeed: settings.maxSpeed,
        minOpacity: settings.minOpacity,
        maxOpacity: settings.maxOpacity,
        explosionRadius: settings.explosionRadius,
        gravity: settings.gravity,
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
    } catch (e) {
      console.warn("Failed to save settings:", e);
    }
  }

  // Load celebration state
  function loadState() {
    try {
      const saved = localStorage.getItem(STORAGE_STATE_KEY);
      return saved === "true";
    } catch (e) {
      return true; // Default to enabled
    }
  }

  // Save celebration state
  function saveState(enabled) {
    try {
      localStorage.setItem(STORAGE_STATE_KEY, enabled ? "true" : "false");
    } catch (e) {
      console.warn("Failed to save state:", e);
    }
  }

  let settings = loadSettings();
  let fireworks = [];
  let particles = [];
  let celebrating = loadState();
  let animationFrame;
  let wrapper = null;
  let menuOpen = false;
  let iconButton = null;
  let menuOverlay = null;
  let menuPanel = null;
  let lastFireworkTime = 0;
  let fireworkInterval = 2000; // ms between fireworks

  // --- Helper Functions ---
  function randomBetween(a, b) {
    return a + Math.random() * (b - a);
  }

  function randomColor() {
    return settings.colors[Math.floor(Math.random() * settings.colors.length)];
  }

  // --- Create or Get Wrapper ---
  function ensureWrapper() {
    let el = document.getElementById("letscelebrate-wrapper");
    if (!el) {
      el = document.createElement("div");
      el.id = "letscelebrate-wrapper";
      Object.assign(el.style, {
        pointerEvents: "none",
        position: "fixed",
        left: 0,
        top: 0,
        width: "100vw",
        height: "100vh",
        zIndex: 5999,
      });
      document.body.appendChild(el);
    }
    return el;
  }

  // --- Create Floating Icon Button ---
  function createIconButton() {
    let btn = document.getElementById("letscelebrate-icon-btn");
    if (btn) return btn;

    btn = document.createElement("button");
    btn.id = "letscelebrate-icon-btn";
    btn.innerHTML = "🎆";
    btn.setAttribute("aria-label", "Celebration Settings");

    // Mobile-friendly sizing - positioned below snow button to avoid collision
    const isMobile = window.innerWidth <= 768;
    const btnSize = isMobile ? "52px" : "56px";
    const btnTop = isMobile ? "120px" : "150px"; // Positioned below snow button
    const btnRight = isMobile ? "16px" : "20px";

    Object.assign(btn.style, {
      position: "fixed",
      top: btnTop,
      right: btnRight,
      bottom: "auto",
      left: "auto",
      width: btnSize,
      height: btnSize,
      borderRadius: "50%",
      background:
        "linear-gradient(135deg, #ff6b6b 0%, #ffd700 50%, #4ecdc4 100%)",
      border: "none",
      color: "#fff",
      fontSize: isMobile ? "22px" : "24px",
      cursor: "pointer",
      zIndex: 9998,
      boxShadow:
        "0 4px 20px rgba(255, 107, 107, 0.4), 0 2px 8px rgba(0, 0, 0, 0.2)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
      userSelect: "none",
      WebkitTapHighlightColor: "transparent",
      touchAction: "manipulation",
    });

    // Hover and active states
    btn.onmouseenter = () => {
      btn.style.transform = "scale(1.1)";
      btn.style.boxShadow =
        "0 6px 25px rgba(255, 107, 107, 0.5), 0 4px 12px rgba(0, 0, 0, 0.3)";
    };
    btn.onmouseleave = () => {
      if (!menuOpen) {
        btn.style.transform = "scale(1)";
        btn.style.boxShadow =
          "0 4px 20px rgba(255, 107, 107, 0.4), 0 2px 8px rgba(0, 0, 0, 0.2)";
      }
    };
    btn.onclick = toggleMenu;

    document.body.appendChild(btn);
    return btn;
  }

  // --- Create Menu Overlay and Panel ---
  function createMenu() {
    // Overlay
    let overlay = document.getElementById("letscelebrate-overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "letscelebrate-overlay";
      Object.assign(overlay.style, {
        position: "fixed",
        top: 0,
        left: 0,
        width: "100vw",
        height: "100vh",
        background: "rgba(0, 0, 0, 0.5)",
        backdropFilter: "blur(4px)",
        zIndex: 9997,
        opacity: 0,
        visibility: "hidden",
        transition: "opacity 0.3s ease, visibility 0.3s ease",
      });
      overlay.onclick = closeMenu;
      document.body.appendChild(overlay);
    }

    // Menu Panel
    let panel = document.getElementById("letscelebrate-menu");
    if (!panel) {
      panel = document.createElement("div");
      panel.id = "letscelebrate-menu";

      // Mobile-friendly positioning - positioned below button at top-right
      const isMobile = window.innerWidth <= 768;
      const btnSize = isMobile ? 52 : 56;
      const btnTop = isMobile ? 120 : 150; // Match button position
      const panelTop = btnTop + btnSize + 12 + "px";
      const panelRight = isMobile ? "16px" : "20px";
      const panelPadding = isMobile ? "22px" : "28px";
      const panelMaxWidth = isMobile ? "none" : "380px";

      Object.assign(panel.style, {
        position: "fixed",
        top: panelTop,
        right: panelRight,
        bottom: "auto",
        left: isMobile ? "16px" : "auto",
        background: "linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%)",
        borderRadius: "20px",
        padding: panelPadding,
        boxShadow:
          "0 25px 70px rgba(0, 0, 0, 0.15), 0 0 0 1px rgba(0, 0, 0, 0.04), inset 0 1px 0 rgba(255, 255, 255, 0.6)",
        zIndex: 9999,
        maxWidth: panelMaxWidth,
        width: isMobile
          ? "calc(100vw - 32px)"
          : "min(calc(100vw - 48px), 380px)",
        maxHeight: "75vh",
        overflowY: "auto",
        transform: "translateY(-20px) scale(0.95)",
        opacity: 0,
        visibility: "hidden",
        transition: "all 0.35s cubic-bezier(0.34, 1.56, 0.64, 1)",
        fontFamily:
          'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif',
        color: "#1a1a1a",
        WebkitOverflowScrolling: "touch",
        border: "1px solid rgba(255, 255, 255, 0.8)",
      });

      // Dark mode support
      const isDark =
        window.matchMedia &&
        window.matchMedia("(prefers-color-scheme: dark)").matches;
      if (isDark) {
        panel.style.background =
          "linear-gradient(135deg, #1e1e2e 0%, #181825 100%)";
        panel.style.color = "#e4e4e7";
        panel.style.border = "1px solid rgba(255, 255, 255, 0.1)";
        panel.style.boxShadow =
          "0 25px 70px rgba(0, 0, 0, 0.4), 0 0 0 1px rgba(255, 255, 255, 0.05), inset 0 1px 0 rgba(255, 255, 255, 0.05)";
      }

      panel.innerHTML = `
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;padding-bottom:20px;border-bottom:1px solid ${
                  isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.08)"
                };">
                    <h2 style="margin:0;font-size:22px;font-weight:700;display:flex;align-items:center;gap:10px;letter-spacing:-0.3px;">
                        <span style="font-size:26px;filter:drop-shadow(0 2px 4px rgba(255,107,107,0.3));">🎆</span>
                        <span>New Year Settings</span>
                    </h2>
                    <button id="letscelebrate-close" style="background:none;border:none;font-size:28px;cursor:pointer;color:inherit;opacity:0.5;padding:0;width:36px;height:36px;display:flex;align-items:center;justify-content:center;border-radius:8px;transition:all 0.2s;line-height:1;" aria-label="Close">×</button>
                </div>
                
                <button id="letscelebrate-toggle" style="width:100%;background:linear-gradient(135deg, #ff6b6b 0%, #ffd700 50%, #4ecdc4 100%);color:#fff;padding:14px 24px;border:none;border-radius:12px;cursor:pointer;font-size:16px;font-weight:600;margin-bottom:28px;transition:all 0.25s cubic-bezier(0.4, 0, 0.2, 1);box-shadow:0 4px 14px rgba(255, 107, 107, 0.35), inset 0 1px 0 rgba(255,255,255,0.2);letter-spacing:0.2px;">
                    ${
                      celebrating ? "⏸ Stop Celebration" : "▶ Start Celebration"
                    }
                </button>
                
                <div style="margin-bottom:24px;padding:16px;background:${
                  isDark ? "rgba(255,255,255,0.03)" : "rgba(0,0,0,0.02)"
                };border-radius:12px;border:1px solid ${
        isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.05)"
      };">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                        <label for="letscelebrate-fireworks" style="font-size:15px;font-weight:600;color:inherit;display:flex;align-items:center;gap:6px;">
                            <span>🎆</span>
                            <span>Fireworks</span>
                        </label>
                        <span id="letscelebrate-fireworks-label" style="font-size:16px;font-weight:700;color:inherit;min-width:50px;text-align:right;background:${
                          isDark
                            ? "rgba(255,107,107,0.15)"
                            : "rgba(255,107,107,0.1)"
                        };padding:4px 12px;border-radius:8px;">${
        settings.fireworkCount
      }</span>
                    </div>
                    <input type="range" id="letscelebrate-fireworks" min="1" max="8" value="${
                      settings.fireworkCount
                    }" 
                        style="width:100%;height:8px;border-radius:4px;background:${
                          isDark ? "#374151" : "#e5e7eb"
                        };outline:none;cursor:pointer;appearance:none;-webkit-appearance:none;">
                    <style>
                        #letscelebrate-fireworks::-webkit-slider-thumb { appearance:none;width:20px;height:20px;border-radius:50%;background:linear-gradient(135deg, #ff6b6b 0%, #ffd700 100%);cursor:pointer;box-shadow:0 3px 8px rgba(255,107,107,0.4), 0 0 0 2px ${
                          isDark
                            ? "rgba(255,107,107,0.2)"
                            : "rgba(255,255,255,0.8)"
                        };transition:all 0.2s; }
                        #letscelebrate-fireworks::-webkit-slider-thumb:hover { transform:scale(1.15);box-shadow:0 4px 12px rgba(255,107,107,0.5), 0 0 0 2px ${
                          isDark
                            ? "rgba(255,107,107,0.3)"
                            : "rgba(255,255,255,0.9)"
                        }; }
                        #letscelebrate-fireworks::-moz-range-thumb { width:20px;height:20px;border-radius:50%;background:linear-gradient(135deg, #ff6b6b 0%, #ffd700 100%);cursor:pointer;border:none;box-shadow:0 3px 8px rgba(255,107,107,0.4);transition:all 0.2s; }
                        #letscelebrate-fireworks::-moz-range-thumb:hover { transform:scale(1.15); }
                    </style>
                </div>
                
                <div style="margin-bottom:24px;padding:16px;background:${
                  isDark ? "rgba(255,255,255,0.03)" : "rgba(0,0,0,0.02)"
                };border-radius:12px;border:1px solid ${
        isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.05)"
      };">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                        <label for="letscelebrate-particles" style="font-size:15px;font-weight:600;color:inherit;display:flex;align-items:center;gap:6px;">
                            <span>✨</span>
                            <span>Particles</span>
                        </label>
                        <span id="letscelebrate-particles-label" style="font-size:16px;font-weight:700;color:inherit;min-width:50px;text-align:right;background:${
                          isDark
                            ? "rgba(255,107,107,0.15)"
                            : "rgba(255,107,107,0.1)"
                        };padding:4px 12px;border-radius:8px;">${
        settings.particleCount
      }</span>
                    </div>
                    <input type="range" id="letscelebrate-particles" min="20" max="150" value="${
                      settings.particleCount
                    }" 
                        style="width:100%;height:8px;border-radius:4px;background:${
                          isDark ? "#374151" : "#e5e7eb"
                        };outline:none;cursor:pointer;appearance:none;-webkit-appearance:none;">
                    <style>
                        #letscelebrate-particles::-webkit-slider-thumb { appearance:none;width:20px;height:20px;border-radius:50%;background:linear-gradient(135deg, #ff6b6b 0%, #ffd700 100%);cursor:pointer;box-shadow:0 3px 8px rgba(255,107,107,0.4), 0 0 0 2px ${
                          isDark
                            ? "rgba(255,107,107,0.2)"
                            : "rgba(255,255,255,0.8)"
                        };transition:all 0.2s; }
                        #letscelebrate-particles::-webkit-slider-thumb:hover { transform:scale(1.15);box-shadow:0 4px 12px rgba(255,107,107,0.5), 0 0 0 2px ${
                          isDark
                            ? "rgba(255,107,107,0.3)"
                            : "rgba(255,255,255,0.9)"
                        }; }
                        #letscelebrate-particles::-moz-range-thumb { width:20px;height:20px;border-radius:50%;background:linear-gradient(135deg, #ff6b6b 0%, #ffd700 100%);cursor:pointer;border:none;box-shadow:0 3px 8px rgba(255,107,107,0.4);transition:all 0.2s; }
                        #letscelebrate-particles::-moz-range-thumb:hover { transform:scale(1.15); }
                    </style>
                </div>
                
                <div style="margin-bottom:28px;padding:16px;background:${
                  isDark ? "rgba(255,255,255,0.03)" : "rgba(0,0,0,0.02)"
                };border-radius:12px;border:1px solid ${
        isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.05)"
      };">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                        <label for="letscelebrate-speed" style="font-size:15px;font-weight:600;color:inherit;display:flex;align-items:center;gap:6px;">
                            <span>⚡</span>
                            <span>Speed</span>
                        </label>
                        <span id="letscelebrate-speed-label" style="font-size:16px;font-weight:700;color:inherit;min-width:50px;text-align:right;background:${
                          isDark
                            ? "rgba(255,107,107,0.15)"
                            : "rgba(255,107,107,0.1)"
                        };padding:4px 12px;border-radius:8px;">${settings.maxSpeed.toFixed(
        1
      )}</span>
                    </div>
                    <input type="range" id="letscelebrate-speed" min="2" max="12" step="0.5" value="${
                      settings.maxSpeed
                    }" 
                        style="width:100%;height:8px;border-radius:4px;background:${
                          isDark ? "#374151" : "#e5e7eb"
                        };outline:none;cursor:pointer;appearance:none;-webkit-appearance:none;">
                    <style>
                        #letscelebrate-speed::-webkit-slider-thumb { appearance:none;width:20px;height:20px;border-radius:50%;background:linear-gradient(135deg, #ff6b6b 0%, #ffd700 100%);cursor:pointer;box-shadow:0 3px 8px rgba(255,107,107,0.4), 0 0 0 2px ${
                          isDark
                            ? "rgba(255,107,107,0.2)"
                            : "rgba(255,255,255,0.8)"
                        };transition:all 0.2s; }
                        #letscelebrate-speed::-webkit-slider-thumb:hover { transform:scale(1.15);box-shadow:0 4px 12px rgba(255,107,107,0.5), 0 0 0 2px ${
                          isDark
                            ? "rgba(255,107,107,0.3)"
                            : "rgba(255,255,255,0.9)"
                        }; }
                        #letscelebrate-speed::-moz-range-thumb { width:20px;height:20px;border-radius:50%;background:linear-gradient(135deg, #ff6b6b 0%, #ffd700 100%);cursor:pointer;border:none;box-shadow:0 3px 8px rgba(255,107,107,0.4);transition:all 0.2s; }
                        #letscelebrate-speed::-moz-range-thumb:hover { transform:scale(1.15); }
                    </style>
                </div>
                
                <button id="letscelebrate-reset" style="width:100%;background:${
                  isDark ? "rgba(255,255,255,0.05)" : "#f3f4f6"
                };color:${
        isDark ? "#e4e4e7" : "#374151"
      };padding:12px 20px;border:1px solid ${
        isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.08)"
      };border-radius:10px;cursor:pointer;font-size:14px;font-weight:600;transition:all 0.2s;letter-spacing:0.3px;">
                    ↻ Reset to Default
                </button>
            `;

      // Additional styling for better appearance
      const style = document.createElement("style");
      style.textContent = `
                #letscelebrate-menu::-webkit-scrollbar { width: 8px; }
                #letscelebrate-menu::-webkit-scrollbar-track { background: ${
                  isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.05)"
                }; border-radius: 4px; }
                #letscelebrate-menu::-webkit-scrollbar-thumb { background: ${
                  isDark ? "rgba(255,255,255,0.2)" : "rgba(0,0,0,0.2)"
                }; border-radius: 4px; }
                #letscelebrate-menu::-webkit-scrollbar-thumb:hover { background: ${
                  isDark ? "rgba(255,255,255,0.3)" : "rgba(0,0,0,0.3)"
                }; }
            `;
      document.head.appendChild(style);

      document.body.appendChild(panel);

      // Close button hover
      const closeBtn = panel.querySelector("#letscelebrate-close");
      if (closeBtn) {
        closeBtn.onmouseenter = () => {
          closeBtn.style.opacity = "1";
          closeBtn.style.background = isDark
            ? "rgba(255,255,255,0.1)"
            : "rgba(0,0,0,0.05)";
          closeBtn.style.transform = "rotate(90deg) scale(1.1)";
        };
        closeBtn.onmouseleave = () => {
          closeBtn.style.opacity = "0.5";
          closeBtn.style.background = "none";
          closeBtn.style.transform = "rotate(0deg) scale(1)";
        };
        closeBtn.onclick = closeMenu;
      }

      // Toggle button hover
      const toggleBtn = panel.querySelector("#letscelebrate-toggle");
      if (toggleBtn) {
        toggleBtn.onmouseenter = () => {
          toggleBtn.style.transform = "translateY(-2px) scale(1.02)";
          toggleBtn.style.boxShadow =
            "0 6px 20px rgba(255, 107, 107, 0.45), inset 0 1px 0 rgba(255,255,255,0.25)";
        };
        toggleBtn.onmouseleave = () => {
          toggleBtn.style.transform = "translateY(0) scale(1)";
          toggleBtn.style.boxShadow =
            "0 4px 14px rgba(255, 107, 107, 0.35), inset 0 1px 0 rgba(255,255,255,0.2)";
        };
      }

      // Reset button hover
      const resetBtn = panel.querySelector("#letscelebrate-reset");
      if (resetBtn) {
        resetBtn.onmouseenter = () => {
          resetBtn.style.background = isDark
            ? "rgba(255,255,255,0.08)"
            : "#e5e7eb";
          resetBtn.style.transform = "translateY(-1px)";
          resetBtn.style.borderColor = isDark
            ? "rgba(255,255,255,0.15)"
            : "rgba(0,0,0,0.12)";
        };
        resetBtn.onmouseleave = () => {
          resetBtn.style.background = isDark
            ? "rgba(255,255,255,0.05)"
            : "#f3f4f6";
          resetBtn.style.transform = "translateY(0)";
          resetBtn.style.borderColor = isDark
            ? "rgba(255,255,255,0.1)"
            : "rgba(0,0,0,0.08)";
        };
      }
    }

    return { overlay, panel };
  }

  function toggleMenu() {
    menuOpen = !menuOpen;
    if (menuOpen) {
      openMenu();
    } else {
      closeMenu();
    }
  }

  function openMenu() {
    if (!menuOverlay || !menuPanel) {
      const menu = createMenu();
      menuOverlay = menu.overlay;
      menuPanel = menu.panel;
    }
    menuOpen = true;
    menuOverlay.style.opacity = "1";
    menuOverlay.style.visibility = "visible";
    menuPanel.style.opacity = "1";
    menuPanel.style.visibility = "visible";
    menuPanel.style.transform = "translateY(0) scale(1) rotate(0deg)";
    if (iconButton) {
      iconButton.style.transform = "scale(1.1) rotate(90deg)";
    }
    document.body.style.overflow = "hidden";
  }

  function closeMenu() {
    if (!menuOverlay || !menuPanel) return;
    menuOpen = false;
    menuOverlay.style.opacity = "0";
    menuOverlay.style.visibility = "hidden";
    menuPanel.style.opacity = "0";
    menuPanel.style.visibility = "hidden";
    menuPanel.style.transform = "translateY(-20px) scale(0.95)";
    if (iconButton) {
      iconButton.style.transform = "scale(1)";
    }
    document.body.style.overflow = "";
  }

  // --- Firework Logic ---
  function createFirework() {
    const x = randomBetween(window.innerWidth * 0.2, window.innerWidth * 0.8);
    const y = window.innerHeight + 20;
    const targetY = randomBetween(
      window.innerHeight * 0.2,
      window.innerHeight * 0.6
    );
    const speed = randomBetween(8, 12);

    const firework = document.createElement("div");
    firework.style.position = "absolute";
    firework.style.left = "0px";
    firework.style.top = "0px";
    firework.style.width = "4px";
    firework.style.height = "4px";
    firework.style.borderRadius = "50%";
    firework.style.background = randomColor();
    firework.style.boxShadow = `0 0 6px ${randomColor()}`;
    firework.style.pointerEvents = "none";
    firework.style.willChange = "transform";

    wrapper.appendChild(firework);

    return {
      el: firework,
      x: x,
      y: y,
      targetY: targetY,
      speed: speed,
      exploded: false,
    };
  }

  function explodeFirework(firework) {
    if (firework.exploded) return;
    firework.exploded = true;
    firework.el.remove();

    const explosionX = firework.x;
    const explosionY = firework.y;
    const color = randomColor();

    for (let i = 0; i < settings.particleCount; i++) {
      const angle = (Math.PI * 2 * i) / settings.particleCount;
      const speed = randomBetween(settings.minSpeed, settings.maxSpeed);
      const vx = Math.cos(angle) * speed;
      const vy = Math.sin(angle) * speed;
      const size = randomBetween(settings.minSize, settings.maxSize);
      const opacity = randomBetween(settings.minOpacity, settings.maxOpacity);
      const particleColor = Math.random() > 0.5 ? color : randomColor();

      const particle = document.createElement("div");
      particle.style.position = "absolute";
      particle.style.left = "0px";
      particle.style.top = "0px";
      particle.style.width = size + "px";
      particle.style.height = size + "px";
      particle.style.borderRadius = "50%";
      particle.style.background = particleColor;
      particle.style.opacity = opacity;
      particle.style.boxShadow = `0 0 ${size * 2}px ${particleColor}`;
      particle.style.pointerEvents = "none";
      particle.style.willChange = "transform";

      wrapper.appendChild(particle);

      particles.push({
        el: particle,
        x: explosionX,
        y: explosionY,
        vx: vx,
        vy: vy,
        size: size,
        opacity: opacity,
        life: 1.0,
        decay: randomBetween(0.01, 0.02),
      });
    }
  }

  function clearAll() {
    for (let firework of fireworks) {
      if (firework && firework.el) firework.el.remove();
    }
    for (let particle of particles) {
      if (particle && particle.el) particle.el.remove();
    }
    fireworks = [];
    particles = [];
  }

  function animate() {
    if (!celebrating) return;

    const now = Date.now();

    // Create new fireworks periodically
    if (now - lastFireworkTime > fireworkInterval) {
      for (let i = 0; i < settings.fireworkCount; i++) {
        setTimeout(() => {
          if (celebrating) {
            fireworks.push(createFirework());
          }
        }, i * 200);
      }
      lastFireworkTime = now;
      fireworkInterval = randomBetween(1500, 3000);
    }

    // Animate fireworks (rising)
    for (let i = fireworks.length - 1; i >= 0; i--) {
      const firework = fireworks[i];
      firework.y -= firework.speed;
      firework.el.style.transform = `translate(${firework.x}px, ${firework.y}px)`;

      if (firework.y <= firework.targetY) {
        explodeFirework(firework);
        fireworks.splice(i, 1);
      }
    }

    // Animate particles (exploding outward)
    for (let i = particles.length - 1; i >= 0; i--) {
      const particle = particles[i];
      particle.x += particle.vx;
      particle.y += particle.vy;
      particle.vy += settings.gravity; // Apply gravity
      particle.life -= particle.decay;
      particle.opacity = particle.life;

      particle.el.style.transform = `translate(${particle.x}px, ${particle.y}px)`;
      particle.el.style.opacity = particle.opacity;

      if (
        particle.life <= 0 ||
        particle.y > window.innerHeight + 50 ||
        particle.x < -50 ||
        particle.x > window.innerWidth + 50
      ) {
        particle.el.remove();
        particles.splice(i, 1);
      }
    }

    animationFrame = requestAnimationFrame(animate);
  }

  function startCelebration() {
    if (celebrating && animationFrame) return; // Already running
    celebrating = true;
    saveState(true);
    wrapper.style.display = "";
    // Set lastFireworkTime to past so first fireworks appear immediately
    lastFireworkTime = Date.now() - fireworkInterval;
    // Clear any existing animation frame
    if (animationFrame) cancelAnimationFrame(animationFrame);
    animate();
    updateToggleBtn();
  }

  function stopCelebration() {
    if (!celebrating) return;
    celebrating = false;
    saveState(false);
    wrapper.style.display = "none";
    if (animationFrame) cancelAnimationFrame(animationFrame);
    clearAll();
    updateToggleBtn();
  }

  function updateToggleBtn() {
    let btn = document.getElementById("letscelebrate-toggle");
    if (btn) {
      btn.innerHTML = celebrating
        ? "⏸ Stop Celebration"
        : "▶ Start Celebration";
    }
  }

  function updateSettingsUI() {
    let fireworksLabel = document.getElementById(
      "letscelebrate-fireworks-label"
    );
    if (fireworksLabel) fireworksLabel.textContent = settings.fireworkCount;
    let particlesLabel = document.getElementById(
      "letscelebrate-particles-label"
    );
    if (particlesLabel) particlesLabel.textContent = settings.particleCount;
    let speedLabel = document.getElementById("letscelebrate-speed-label");
    if (speedLabel) speedLabel.textContent = settings.maxSpeed.toFixed(1);
  }

  // --- Events & GUI Logic ---
  function attachControlEvents() {
    document.addEventListener("click", (e) => {
      if (
        e.target.id === "letscelebrate-toggle" ||
        e.target.closest("#letscelebrate-toggle")
      ) {
        e.preventDefault();
        e.stopPropagation();
        if (celebrating) stopCelebration();
        else {
          startCelebration();
        }
      }
    });

    document.addEventListener("input", (e) => {
      if (e.target.id === "letscelebrate-fireworks") {
        settings.fireworkCount = parseInt(e.target.value, 10);
        updateSettingsUI();
        saveSettings();
      } else if (e.target.id === "letscelebrate-particles") {
        settings.particleCount = parseInt(e.target.value, 10);
        updateSettingsUI();
        saveSettings();
      } else if (e.target.id === "letscelebrate-speed") {
        let val = parseFloat(e.target.value);
        settings.maxSpeed = val;
        updateSettingsUI();
        saveSettings();
      }
    });

    document.addEventListener("click", (e) => {
      if (
        e.target.id === "letscelebrate-reset" ||
        e.target.closest("#letscelebrate-reset")
      ) {
        e.preventDefault();
        e.stopPropagation();
        settings = { ...DEFAULTS };
        saveSettings();
        const fireworksInput = document.getElementById(
          "letscelebrate-fireworks"
        );
        const particlesInput = document.getElementById(
          "letscelebrate-particles"
        );
        const speedInput = document.getElementById("letscelebrate-speed");
        if (fireworksInput) fireworksInput.value = settings.fireworkCount;
        if (particlesInput) particlesInput.value = settings.particleCount;
        if (speedInput) speedInput.value = settings.maxSpeed;
        updateSettingsUI();
      }
    });
  }

  // --- Responsive Resize ---
  window.addEventListener("resize", () => {
    // Clear particles that are off-screen
    for (let i = particles.length - 1; i >= 0; i--) {
      const particle = particles[i];
      if (
        particle.x < -100 ||
        particle.x > window.innerWidth + 100 ||
        particle.y > window.innerHeight + 100
      ) {
        particle.el.remove();
        particles.splice(i, 1);
      }
    }

    // Update button and menu positioning for mobile
    if (iconButton) {
      const isMobile = window.innerWidth <= 768;
      iconButton.style.width = isMobile ? "52px" : "56px";
      iconButton.style.height = isMobile ? "52px" : "56px";
      iconButton.style.fontSize = isMobile ? "22px" : "24px";
      iconButton.style.top = isMobile ? "120px" : "150px";
      iconButton.style.right = isMobile ? "16px" : "20px";
      iconButton.style.bottom = "auto";
      iconButton.style.left = "auto";
    }

    if (menuPanel) {
      const isMobile = window.innerWidth <= 768;
      const btnSize = isMobile ? 52 : 56;
      const btnTop = isMobile ? 120 : 150;
      const panelTop = btnTop + btnSize + 12 + "px";
      menuPanel.style.top = panelTop;
      menuPanel.style.right = isMobile ? "16px" : "20px";
      menuPanel.style.bottom = "auto";
      menuPanel.style.left = isMobile ? "16px" : "auto";
      menuPanel.style.width = isMobile
        ? "calc(100vw - 32px)"
        : "min(calc(100vw - 48px), 380px)";
      menuPanel.style.maxWidth = isMobile ? "none" : "380px";
      menuPanel.style.padding = isMobile ? "22px" : "28px";
    }
  });

  // --- Setup ---
  wrapper = ensureWrapper();
  iconButton = createIconButton();
  attachControlEvents();

  // Start celebration if it was enabled before
  if (celebrating) {
    startCelebration();
  } else {
    wrapper.style.display = "none";
  }

  // Toggle menu on keyboard shortcut: Ctrl+Shift+C
  window.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.shiftKey && e.key.toUpperCase() === "C") {
      e.preventDefault();
      toggleMenu();
    }
    // Close menu on Escape
    if (e.key === "Escape" && menuOpen) {
      closeMenu();
    }
  });

  // Prevent menu from closing when clicking inside it
  document.addEventListener("click", (e) => {
    if (
      menuPanel &&
      menuPanel.contains(e.target) &&
      e.target.id !== "letscelebrate-close"
    ) {
      e.stopPropagation();
    }
  });
})();
