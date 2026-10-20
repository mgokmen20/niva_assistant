import './index.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { AuthModal } from './components/AuthModal.tsx'
import { AuthProvider } from './context/AuthContext.tsx'
import { LanguageProvider } from './context/LanguageContext.tsx'
import { SeniorModeProvider } from './context/SeniorModeContext.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <LanguageProvider>
        <SeniorModeProvider>
          <App />
          <AuthModal />
        </SeniorModeProvider>
      </LanguageProvider>
    </AuthProvider>
  </StrictMode>,
)
