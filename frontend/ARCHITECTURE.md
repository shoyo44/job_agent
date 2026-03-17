# Frontend Architecture Guide

This frontend is built for **Production Readiness** and **Developer Support**. It follows a modular architecture that separates concerns, making it easy to understand, maintain, and scale.

## 📁 Directory Structure

- **`/src/components`**: Modular UI components.
  - `LoginScreen.tsx`: Entry portal using Firebase Auth.
  - `OnboardingFlow.tsx`: Transient credential collection.
  - `DashboardLayout.tsx`: Main application shell with navigation and "Quick Guide".
  - `OverviewPanel.tsx`: System-wide health and KPI visualization.
  - `PipelineConfig.tsx`: Functional configuration for agent runs.
  - `ExecutionOutput.tsx`: Real-time feedback and raw diagnostic logs.
- **`/src/services`**: API abstraction layer.
- **`/src/types`**: Centralized TypeScript definitions.
- **`/src/hooks`**: Custom React hooks (e.g., `useRunForm`) for shared logic.

## 💎 Design System

The system is powered by **CSS Variables** defined in `index.css`. This ensures that altering the look and feel (e.g., switching to a Dark Mode) is a one-file change.

- **Clean Boundaries**: Every component is wrapped in a `.panel` with consistent padding and shadows.
- **Supportive UX**: Staggered animations (`.staggered`) provide visual confirmation of state changes without being distracting.
- **Clear Tone**: We use a grayscale palette to convey a professional, "mission control" atmosphere.

## 🚀 Running in Production

1.  **Environment**: Ensure `VITE_API_BASE_URL` is set to your production backend.
2.  **Build**: Run `npm run build` to generate the optimized asset bundle.
3.  **Deploy**: The project is compatible with Vercel, Netlify, or static hosting.
