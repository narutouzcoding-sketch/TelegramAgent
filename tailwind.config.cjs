module.exports = {
  "content": [
    "./telegram_agent/panel_web/*.html",
    "./telegram_agent/panel_web/*.js"
  ],
  "darkMode": "class",
  "theme": {
    "extend": {
      "colors": {
        "surface": "rgb(var(--color-surface) / <alpha-value>)",
        "on-tertiary-fixed": "rgb(var(--color-on-tertiary-fixed) / <alpha-value>)",
        "on-surface-variant": "rgb(var(--color-on-surface-variant) / <alpha-value>)",
        "surface-container-low": "rgb(var(--color-surface-container-low) / <alpha-value>)",
        "on-tertiary-container": "rgb(var(--color-on-tertiary-container) / <alpha-value>)",
        "on-surface": "rgb(var(--color-on-surface) / <alpha-value>)",
        "surface-container-high": "rgb(var(--color-surface-container-high) / <alpha-value>)",
        "secondary": "rgb(var(--color-secondary) / <alpha-value>)",
        "on-background": "rgb(var(--color-on-background) / <alpha-value>)",
        "primary-fixed-dim": "rgb(var(--color-primary-fixed-dim) / <alpha-value>)",
        "on-secondary-fixed": "rgb(var(--color-on-secondary-fixed) / <alpha-value>)",
        "secondary-fixed": "rgb(var(--color-secondary-fixed) / <alpha-value>)",
        "secondary-container": "rgb(var(--color-secondary-container) / <alpha-value>)",
        "surface-variant": "rgb(var(--color-surface-variant) / <alpha-value>)",
        "inverse-surface": "rgb(var(--color-inverse-surface) / <alpha-value>)",
        "tertiary-container": "rgb(var(--color-tertiary-container) / <alpha-value>)",
        "surface-dim": "rgb(var(--color-surface-dim) / <alpha-value>)",
        "error": "rgb(var(--color-error) / <alpha-value>)",
        "background": "rgb(var(--color-background) / <alpha-value>)",
        "on-error": "rgb(var(--color-on-error) / <alpha-value>)",
        "surface-tint": "rgb(var(--color-surface-tint) / <alpha-value>)",
        "on-secondary-container": "rgb(var(--color-on-secondary-container) / <alpha-value>)",
        "surface-container-lowest": "rgb(var(--color-surface-container-lowest) / <alpha-value>)",
        "on-tertiary": "rgb(var(--color-on-tertiary) / <alpha-value>)",
        "surface-container": "rgb(var(--color-surface-container) / <alpha-value>)",
        "on-secondary": "rgb(var(--color-on-secondary) / <alpha-value>)",
        "primary-container": "rgb(var(--color-primary-container) / <alpha-value>)",
        "on-primary-container": "rgb(var(--color-on-primary-container) / <alpha-value>)",
        "on-tertiary-fixed-variant": "rgb(var(--color-on-tertiary-fixed-variant) / <alpha-value>)",
        "inverse-primary": "rgb(var(--color-inverse-primary) / <alpha-value>)",
        "tertiary-fixed": "rgb(var(--color-tertiary-fixed) / <alpha-value>)",
        "outline-variant": "rgb(var(--color-outline-variant) / <alpha-value>)",
        "on-primary-fixed-variant": "rgb(var(--color-on-primary-fixed-variant) / <alpha-value>)",
        "surface-container-highest": "rgb(var(--color-surface-container-highest) / <alpha-value>)",
        "inverse-on-surface": "rgb(var(--color-inverse-on-surface) / <alpha-value>)",
        "primary": "rgb(var(--color-primary) / <alpha-value>)",
        "tertiary-fixed-dim": "rgb(var(--color-tertiary-fixed-dim) / <alpha-value>)",
        "secondary-fixed-dim": "rgb(var(--color-secondary-fixed-dim) / <alpha-value>)",
        "on-secondary-fixed-variant": "rgb(var(--color-on-secondary-fixed-variant) / <alpha-value>)",
        "on-primary-fixed": "rgb(var(--color-on-primary-fixed) / <alpha-value>)",
        "on-error-container": "rgb(var(--color-on-error-container) / <alpha-value>)",
        "outline": "rgb(var(--color-outline) / <alpha-value>)",
        "tertiary": "rgb(var(--color-tertiary) / <alpha-value>)",
        "on-primary": "rgb(var(--color-on-primary) / <alpha-value>)",
        "surface-bright": "rgb(var(--color-surface-bright) / <alpha-value>)",
        "error-container": "rgb(var(--color-error-container) / <alpha-value>)",
        "primary-fixed": "rgb(var(--color-primary-fixed) / <alpha-value>)"
      },
      "borderRadius": {
        "DEFAULT": "0.25rem",
        "lg": "0.5rem",
        "xl": "0.75rem",
        "full": "9999px"
      },
      "spacing": {
        "margin": "1rem",
        "space-xxs": "0.25rem",
        "margin-md": "1.5rem",
        "space-lg": "1.25rem",
        "space-sm": "0.5rem",
        "margin-lg": "2rem",
        "space-xs": "0.375rem",
        "space-base": "1rem",
        "gutter-lg": "1.5rem",
        "space-2xl": "2rem",
        "space-md": "0.75rem",
        "space-xl": "1.5rem",
        "gutter": "1rem"
      },
      "fontFamily": {
        "body-lg": [
          "Inter",
          "sans-serif"
        ],
        "label-sm": [
          "Inter",
          "sans-serif"
        ],
        "body-md": [
          "Inter",
          "sans-serif"
        ],
        "label-md": [
          "Inter",
          "sans-serif"
        ],
        "headline-xl": [
          "Inter",
          "sans-serif"
        ],
        "headline-lg": [
          "Inter",
          "sans-serif"
        ],
        "headline-sm": [
          "Inter",
          "sans-serif"
        ],
        "headline-md": [
          "Inter",
          "sans-serif"
        ],
        "code-sm": [
          "Inter",
          "sans-serif"
        ],
        "body-sm": [
          "Inter",
          "sans-serif"
        ]
      },
      "fontSize": {
        "body-lg": [
          "14px",
          {
            "lineHeight": "20px",
            "letterSpacing": "0em",
            "fontWeight": "400"
          }
        ],
        "label-sm": [
          "11px",
          {
            "lineHeight": "14px",
            "letterSpacing": "0.02em",
            "fontWeight": "600"
          }
        ],
        "body-md": [
          "13px",
          {
            "lineHeight": "18px",
            "letterSpacing": "0em",
            "fontWeight": "400"
          }
        ],
        "label-md": [
          "13px",
          {
            "lineHeight": "18px",
            "letterSpacing": "0em",
            "fontWeight": "500"
          }
        ],
        "headline-xl": [
          "28px",
          {
            "lineHeight": "34px",
            "letterSpacing": "-0.02em",
            "fontWeight": "600"
          }
        ],
        "headline-lg": [
          "22px",
          {
            "lineHeight": "28px",
            "letterSpacing": "-0.015em",
            "fontWeight": "600"
          }
        ],
        "headline-sm": [
          "15px",
          {
            "lineHeight": "20px",
            "letterSpacing": "-0.005em",
            "fontWeight": "600"
          }
        ],
        "headline-md": [
          "18px",
          {
            "lineHeight": "24px",
            "letterSpacing": "-0.01em",
            "fontWeight": "600"
          }
        ],
        "code-sm": [
          "12px",
          {
            "lineHeight": "16px",
            "letterSpacing": "0em",
            "fontWeight": "400"
          }
        ],
        "body-sm": [
          "12px",
          {
            "lineHeight": "16px",
            "letterSpacing": "0.005em",
            "fontWeight": "400"
          }
        ]
      }
    }
  }
};
