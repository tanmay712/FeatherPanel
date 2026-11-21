(function () {
  // --- Default Snow Settings ---
  const DEFAULTS = {
    snowflakeCount: 80,
    minSize: 6,
    maxSize: 18,
    minSpeedY: 0.8,
    maxSpeedY: 2.2,
    minSpeedX: -0.4,
    maxSpeedX: 0.4,
    minSway: 1,
    maxSway: 2,
    minOpacity: 0.6,
    maxOpacity: 1.0,
    colors: ["#fff", "#e0f7fa", "#fffde7", "#e3f2fd"],
  };

  // --- State ---
  const STORAGE_KEY = "letitsnow-settings";
  const STORAGE_STATE_KEY = "letitsnow-state";

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
        snowflakeCount: settings.snowflakeCount,
        minSize: settings.minSize,
        maxSize: settings.maxSize,
        minSpeedY: settings.minSpeedY,
        maxSpeedY: settings.maxSpeedY,
        minSpeedX: settings.minSpeedX,
        maxSpeedX: settings.maxSpeedX,
        minSway: settings.minSway,
        maxSway: settings.maxSway,
        minOpacity: settings.minOpacity,
        maxOpacity: settings.maxOpacity,
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
    } catch (e) {
      console.warn("Failed to save settings:", e);
    }
  }

  // Load snow state
  function loadState() {
    try {
      const saved = localStorage.getItem(STORAGE_STATE_KEY);
      return saved !== "false"; // Default to enabled
    } catch (e) {
      return true; // Default to enabled
    }
  }

  // Save snow state
  function saveState(enabled) {
    try {
      localStorage.setItem(STORAGE_STATE_KEY, enabled ? "true" : "false");
    } catch (e) {
      console.warn("Failed to save state:", e);
    }
  }

  let settings = loadSettings();
  let snowflakes = [];
  let snowing = loadState();
  let animationFrame;
  let snowWrapper = null;
  let menuOpen = false;
  let iconButton = null;
  let menuOverlay = null;
  let menuPanel = null;

  // --- Helper Functions ---
  function randomBetween(a, b) {
    return a + Math.random() * (b - a);
  }

  // --- Create or Get Snow Wrapper ---
  function ensureSnowWrapper() {
    let el = document.getElementById("letitsnow-wrapper");
    if (!el) {
      el = document.createElement("div");
      el.id = "letitsnow-wrapper";
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
    let btn = document.getElementById("letitsnow-icon-btn");
    if (btn) return btn;

    btn = document.createElement("button");
    btn.id = "letitsnow-icon-btn";
    btn.innerHTML = "❄️";
    btn.setAttribute("aria-label", "Snow Settings");

    // Mobile-friendly sizing - positioned at top-right to avoid sidebar and chatbot
    const isMobile = window.innerWidth <= 768;
    const btnSize = isMobile ? "52px" : "56px";
    const btnTop = isMobile ? "60px" : "80px";
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
      background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
      border: "none",
      color: "#fff",
      fontSize: isMobile ? "22px" : "24px",
      cursor: "pointer",
      zIndex: 9998,
      boxShadow:
        "0 4px 20px rgba(102, 126, 234, 0.4), 0 2px 8px rgba(0, 0, 0, 0.2)",
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
        "0 6px 25px rgba(102, 126, 234, 0.5), 0 4px 12px rgba(0, 0, 0, 0.3)";
    };
    btn.onmouseleave = () => {
      if (!menuOpen) {
        btn.style.transform = "scale(1)";
        btn.style.boxShadow =
          "0 4px 20px rgba(102, 126, 234, 0.4), 0 2px 8px rgba(0, 0, 0, 0.2)";
      }
    };
    btn.onclick = toggleMenu;

    document.body.appendChild(btn);
    return btn;
  }

  // --- Create Menu Overlay and Panel ---
  function createMenu() {
    // Overlay
    let overlay = document.getElementById("letitsnow-overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "letitsnow-overlay";
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
    let panel = document.getElementById("letitsnow-menu");
    if (!panel) {
      panel = document.createElement("div");
      panel.id = "letitsnow-menu";

      // Mobile-friendly positioning - positioned below button at top-right
      const isMobile = window.innerWidth <= 768;
      const btnSize = isMobile ? 52 : 56;
      const btnTop = isMobile ? 60 : 80;
      const panelTop = btnTop + btnSize + 12 + "px"; // Button height + spacing
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
                        <span style="font-size:26px;filter:drop-shadow(0 2px 4px rgba(102,126,234,0.3));">❄️</span>
                        <span>Snow Settings</span>
                    </h2>
                    <button id="letitsnow-close" style="background:none;border:none;font-size:28px;cursor:pointer;color:inherit;opacity:0.5;padding:0;width:36px;height:36px;display:flex;align-items:center;justify-content:center;border-radius:8px;transition:all 0.2s;line-height:1;" aria-label="Close">×</button>
                </div>
                
                <button id="letitsnow-toggle" style="width:100%;background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);color:#fff;padding:14px 24px;border:none;border-radius:12px;cursor:pointer;font-size:16px;font-weight:600;margin-bottom:28px;transition:all 0.25s cubic-bezier(0.4, 0, 0.2, 1);box-shadow:0 4px 14px rgba(102, 126, 234, 0.35), inset 0 1px 0 rgba(255,255,255,0.2);letter-spacing:0.2px;">
                    ${snowing ? "⏸ Stop Snow" : "▶ Start Snow"}
                </button>
                
                <div style="margin-bottom:24px;padding:16px;background:${
                  isDark ? "rgba(255,255,255,0.03)" : "rgba(0,0,0,0.02)"
                };border-radius:12px;border:1px solid ${
        isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.05)"
      };">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                        <label for="letitsnow-count" style="font-size:15px;font-weight:600;color:inherit;display:flex;align-items:center;gap:6px;">
                            <span>❄</span>
                            <span>Snowflakes</span>
                        </label>
                        <span id="letitsnow-count-label" style="font-size:16px;font-weight:700;color:inherit;min-width:50px;text-align:right;background:${
                          isDark
                            ? "rgba(102,126,234,0.15)"
                            : "rgba(102,126,234,0.1)"
                        };padding:4px 12px;border-radius:8px;">${
        settings.snowflakeCount
      }</span>
                    </div>
                    <input type="range" id="letitsnow-count" min="10" max="300" value="${
                      settings.snowflakeCount
                    }" 
                        style="width:100%;height:8px;border-radius:4px;background:${
                          isDark ? "#374151" : "#e5e7eb"
                        };outline:none;cursor:pointer;appearance:none;-webkit-appearance:none;">
                    <style>
                        #letitsnow-count::-webkit-slider-thumb { appearance:none;width:20px;height:20px;border-radius:50%;background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);cursor:pointer;box-shadow:0 3px 8px rgba(102,126,234,0.4), 0 0 0 2px ${
                          isDark
                            ? "rgba(102,126,234,0.2)"
                            : "rgba(255,255,255,0.8)"
                        };transition:all 0.2s; }
                        #letitsnow-count::-webkit-slider-thumb:hover { transform:scale(1.15);box-shadow:0 4px 12px rgba(102,126,234,0.5), 0 0 0 2px ${
                          isDark
                            ? "rgba(102,126,234,0.3)"
                            : "rgba(255,255,255,0.9)"
                        }; }
                        #letitsnow-count::-moz-range-thumb { width:20px;height:20px;border-radius:50%;background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);cursor:pointer;border:none;box-shadow:0 3px 8px rgba(102,126,234,0.4);transition:all 0.2s; }
                        #letitsnow-count::-moz-range-thumb:hover { transform:scale(1.15); }
                    </style>
                </div>
                
                <div style="margin-bottom:24px;padding:16px;background:${
                  isDark ? "rgba(255,255,255,0.03)" : "rgba(0,0,0,0.02)"
                };border-radius:12px;border:1px solid ${
        isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.05)"
      };">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                        <label for="letitsnow-size" style="font-size:15px;font-weight:600;color:inherit;display:flex;align-items:center;gap:6px;">
                            <span>📏</span>
                            <span>Size</span>
                        </label>
                        <span id="letitsnow-size-label" style="font-size:16px;font-weight:700;color:inherit;min-width:50px;text-align:right;background:${
                          isDark
                            ? "rgba(102,126,234,0.15)"
                            : "rgba(102,126,234,0.1)"
                        };padding:4px 12px;border-radius:8px;">${
        settings.maxSize
      }px</span>
                    </div>
                    <input type="range" id="letitsnow-size" min="4" max="40" value="${
                      settings.maxSize
                    }" 
                        style="width:100%;height:8px;border-radius:4px;background:${
                          isDark ? "#374151" : "#e5e7eb"
                        };outline:none;cursor:pointer;appearance:none;-webkit-appearance:none;">
                    <style>
                        #letitsnow-size::-webkit-slider-thumb { appearance:none;width:20px;height:20px;border-radius:50%;background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);cursor:pointer;box-shadow:0 3px 8px rgba(102,126,234,0.4), 0 0 0 2px ${
                          isDark
                            ? "rgba(102,126,234,0.2)"
                            : "rgba(255,255,255,0.8)"
                        };transition:all 0.2s; }
                        #letitsnow-size::-webkit-slider-thumb:hover { transform:scale(1.15);box-shadow:0 4px 12px rgba(102,126,234,0.5), 0 0 0 2px ${
                          isDark
                            ? "rgba(102,126,234,0.3)"
                            : "rgba(255,255,255,0.9)"
                        }; }
                        #letitsnow-size::-moz-range-thumb { width:20px;height:20px;border-radius:50%;background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);cursor:pointer;border:none;box-shadow:0 3px 8px rgba(102,126,234,0.4);transition:all 0.2s; }
                        #letitsnow-size::-moz-range-thumb:hover { transform:scale(1.15); }
                    </style>
                </div>
                
                <div style="margin-bottom:28px;padding:16px;background:${
                  isDark ? "rgba(255,255,255,0.03)" : "rgba(0,0,0,0.02)"
                };border-radius:12px;border:1px solid ${
        isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.05)"
      };">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                        <label for="letitsnow-speed" style="font-size:15px;font-weight:600;color:inherit;display:flex;align-items:center;gap:6px;">
                            <span>⚡</span>
                            <span>Speed</span>
                        </label>
                        <span id="letitsnow-speed-label" style="font-size:16px;font-weight:700;color:inherit;min-width:50px;text-align:right;background:${
                          isDark
                            ? "rgba(102,126,234,0.15)"
                            : "rgba(102,126,234,0.1)"
                        };padding:4px 12px;border-radius:8px;">${settings.maxSpeedY.toFixed(
        1
      )}</span>
                    </div>
                    <input type="range" id="letitsnow-speed" min="0.5" max="5" step="0.1" value="${
                      settings.maxSpeedY
                    }" 
                        style="width:100%;height:8px;border-radius:4px;background:${
                          isDark ? "#374151" : "#e5e7eb"
                        };outline:none;cursor:pointer;appearance:none;-webkit-appearance:none;">
                    <style>
                        #letitsnow-speed::-webkit-slider-thumb { appearance:none;width:20px;height:20px;border-radius:50%;background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);cursor:pointer;box-shadow:0 3px 8px rgba(102,126,234,0.4), 0 0 0 2px ${
                          isDark
                            ? "rgba(102,126,234,0.2)"
                            : "rgba(255,255,255,0.8)"
                        };transition:all 0.2s; }
                        #letitsnow-speed::-webkit-slider-thumb:hover { transform:scale(1.15);box-shadow:0 4px 12px rgba(102,126,234,0.5), 0 0 0 2px ${
                          isDark
                            ? "rgba(102,126,234,0.3)"
                            : "rgba(255,255,255,0.9)"
                        }; }
                        #letitsnow-speed::-moz-range-thumb { width:20px;height:20px;border-radius:50%;background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);cursor:pointer;border:none;box-shadow:0 3px 8px rgba(102,126,234,0.4);transition:all 0.2s; }
                        #letitsnow-speed::-moz-range-thumb:hover { transform:scale(1.15); }
                    </style>
                </div>
                
                <button id="letitsnow-reset" style="width:100%;background:${
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
                #letitsnow-menu::-webkit-scrollbar { width: 8px; }
                #letitsnow-menu::-webkit-scrollbar-track { background: ${
                  isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.05)"
                }; border-radius: 4px; }
                #letitsnow-menu::-webkit-scrollbar-thumb { background: ${
                  isDark ? "rgba(255,255,255,0.2)" : "rgba(0,0,0,0.2)"
                }; border-radius: 4px; }
                #letitsnow-menu::-webkit-scrollbar-thumb:hover { background: ${
                  isDark ? "rgba(255,255,255,0.3)" : "rgba(0,0,0,0.3)"
                }; }
            `;
      document.head.appendChild(style);

      document.body.appendChild(panel);

      // Close button hover
      const closeBtn = panel.querySelector("#letitsnow-close");
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
      const toggleBtn = panel.querySelector("#letitsnow-toggle");
      if (toggleBtn) {
        toggleBtn.onmouseenter = () => {
          toggleBtn.style.transform = "translateY(-2px) scale(1.02)";
          toggleBtn.style.boxShadow =
            "0 6px 20px rgba(102, 126, 234, 0.45), inset 0 1px 0 rgba(255,255,255,0.25)";
        };
        toggleBtn.onmouseleave = () => {
          toggleBtn.style.transform = "translateY(0) scale(1)";
          toggleBtn.style.boxShadow =
            "0 4px 14px rgba(102, 126, 234, 0.35), inset 0 1px 0 rgba(255,255,255,0.2)";
        };
      }

      // Reset button hover
      const resetBtn = panel.querySelector("#letitsnow-reset");
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

  // --- Snowflake Logic ---
  function createSnowflake() {
    const flake = document.createElement("div");
    const size = randomBetween(settings.minSize, settings.maxSize);
    const left = randomBetween(0, window.innerWidth - size);
    const opacity = randomBetween(settings.minOpacity, settings.maxOpacity);
    const color =
      settings.colors[Math.floor(Math.random() * settings.colors.length)];
    flake.style.position = "absolute";
    flake.style.top = -size + "px";
    flake.style.left = left + "px";
    flake.style.width = size + "px";
    flake.style.height = size + "px";
    flake.style.borderRadius = "50%";
    flake.style.background = color;
    flake.style.opacity = opacity;
    flake.style.boxShadow = `0 1px 7px 0 ${color}77`;
    flake.style.pointerEvents = "none";
    flake.style.willChange = "transform";

    snowWrapper.appendChild(flake);

    return {
      el: flake,
      x: left,
      y: -size,
      speedY: randomBetween(settings.minSpeedY, settings.maxSpeedY),
      speedX: randomBetween(settings.minSpeedX, settings.maxSpeedX),
      sway: randomBetween(settings.minSway, settings.maxSway),
      swayStep: randomBetween(0, Math.PI * 2),
      size,
    };
  }

  function clearSnowflakes() {
    for (let flake of snowflakes) {
      if (flake && flake.el) flake.el.remove();
    }
    snowflakes = [];
  }

  function initSnowflakes() {
    clearSnowflakes();
    for (let i = 0; i < settings.snowflakeCount; i++) {
      snowflakes.push(createSnowflake());
    }
  }

  function moveSnowflakes() {
    if (!snowing) return;
    for (let flake of snowflakes) {
      flake.swayStep += 0.01 + randomBetween(0, 0.007);
      flake.x += Math.sin(flake.swayStep) * flake.sway + flake.speedX;
      flake.y += flake.speedY;
      flake.el.style.transform = `translate(${flake.x}px, ${flake.y}px)`;
      // offscreen? reset to top
      if (
        flake.y > window.innerHeight ||
        flake.x < -flake.size ||
        flake.x > window.innerWidth + flake.size
      ) {
        flake.x = randomBetween(0, window.innerWidth - flake.size);
        flake.y = -flake.size;
        flake.swayStep = randomBetween(0, Math.PI * 2);
      }
    }
    animationFrame = requestAnimationFrame(moveSnowflakes);
  }

  function startSnow() {
    if (snowing) return;
    snowing = true;
    saveState(true);
    snowWrapper.style.display = "";
    moveSnowflakes();
    updateToggleBtn();
  }

  function stopSnow() {
    if (!snowing) return;
    snowing = false;
    saveState(false);
    snowWrapper.style.display = "none";
    if (animationFrame) cancelAnimationFrame(animationFrame);
    updateToggleBtn();
  }

  function updateToggleBtn() {
    let btn = document.getElementById("letitsnow-toggle");
    if (btn) {
      btn.innerHTML = snowing ? "⏸ Stop Snow" : "▶ Start Snow";
    }
  }

  function updateSettingsUI() {
    let count = document.getElementById("letitsnow-count-label");
    if (count) count.textContent = settings.snowflakeCount;
    let size = document.getElementById("letitsnow-size-label");
    if (size) size.textContent = settings.maxSize + "px";
    let speed = document.getElementById("letitsnow-speed-label");
    if (speed) speed.textContent = settings.maxSpeedY.toFixed(1);
  }

  // --- Events & GUI Logic ---
  function attachControlEvents() {
    // Use event delegation since menu might not exist yet
    document.addEventListener("click", (e) => {
      if (
        e.target.id === "letitsnow-toggle" ||
        e.target.closest("#letitsnow-toggle")
      ) {
        e.preventDefault();
        e.stopPropagation();
        if (snowing) stopSnow();
        else {
          startSnow();
          moveSnowflakes();
        }
      }
    });

    document.addEventListener("input", (e) => {
      if (e.target.id === "letitsnow-count") {
        settings.snowflakeCount = parseInt(e.target.value, 10);
        updateSettingsUI();
        saveSettings();
        initSnowflakes();
      } else if (e.target.id === "letitsnow-size") {
        settings.maxSize = parseInt(e.target.value, 10);
        updateSettingsUI();
        saveSettings();
        initSnowflakes();
      } else if (e.target.id === "letitsnow-speed") {
        let val = parseFloat(e.target.value);
        settings.maxSpeedY = val;
        updateSettingsUI();
        saveSettings();
        initSnowflakes();
      }
    });

    document.addEventListener("click", (e) => {
      if (
        e.target.id === "letitsnow-reset" ||
        e.target.closest("#letitsnow-reset")
      ) {
        e.preventDefault();
        e.stopPropagation();
        settings = { ...DEFAULTS };
        saveSettings();
        const countInput = document.getElementById("letitsnow-count");
        const sizeInput = document.getElementById("letitsnow-size");
        const speedInput = document.getElementById("letitsnow-speed");
        if (countInput) countInput.value = settings.snowflakeCount;
        if (sizeInput) sizeInput.value = settings.maxSize;
        if (speedInput) speedInput.value = settings.maxSpeedY;
        updateSettingsUI();
        initSnowflakes();
      }
    });
  }

  // --- Responsive Resize ---
  window.addEventListener("resize", () => {
    // Update snowflake positions
    for (let flake of snowflakes) {
      if (flake.x > window.innerWidth) {
        flake.x = randomBetween(0, window.innerWidth - flake.size);
      }
    }

    // Update button and menu positioning for mobile
    if (iconButton) {
      const isMobile = window.innerWidth <= 768;
      iconButton.style.width = isMobile ? "52px" : "56px";
      iconButton.style.height = isMobile ? "52px" : "56px";
      iconButton.style.fontSize = isMobile ? "22px" : "24px";
      iconButton.style.top = isMobile ? "60px" : "80px";
      iconButton.style.right = isMobile ? "16px" : "20px";
      iconButton.style.bottom = "auto";
      iconButton.style.left = "auto";
    }

    if (menuPanel) {
      const isMobile = window.innerWidth <= 768;
      const btnSize = isMobile ? 52 : 56;
      const btnTop = isMobile ? 60 : 80;
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
  snowWrapper = ensureSnowWrapper();
  iconButton = createIconButton();
  attachControlEvents();

  // Start snow if it was enabled before
  if (snowing) {
    initSnowflakes();
    moveSnowflakes();
  } else {
    snowWrapper.style.display = "none";
  }

  // Toggle menu on keyboard shortcut: Ctrl+Shift+S
  window.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.shiftKey && e.key.toUpperCase() === "S") {
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
      e.target.id !== "letitsnow-close"
    ) {
      e.stopPropagation();
    }
  });
})();
