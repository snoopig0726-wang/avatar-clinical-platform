import { lazy, Suspense, type ComponentType } from 'react'
import { Route, Routes } from 'react-router-dom'

function loadNamed<T extends Record<string, ComponentType>>(
  loader: () => Promise<T>,
  name: keyof T,
) {
  return lazy(async () => {
    const module = await loader()
    return { default: module[name] }
  })
}

const LandingPage = loadNamed(() => import('../pages/LandingPage'), 'LandingPage')
const DoctorLoginPage = loadNamed(() => import('../pages/DoctorLoginPage'), 'DoctorLoginPage')
const DoctorApplicationPage = loadNamed(
  () => import('../pages/DoctorApplicationPage'),
  'DoctorApplicationPage',
)
const DoctorWorkspacePage = loadNamed(
  () => import('../pages/DoctorWorkspacePage'),
  'DoctorWorkspacePage',
)
const DoctorCasePage = loadNamed(() => import('../pages/DoctorCasePage'), 'DoctorCasePage')
const DoctorInterviewPage = loadNamed(
  () => import('../pages/DoctorInterviewPage'),
  'DoctorInterviewPage',
)
const PatientInvitePage = loadNamed(
  () => import('../pages/PatientInvitePage'),
  'PatientInvitePage',
)
const PatientWaitingPage = loadNamed(
  () => import('../pages/PatientWaitingPage'),
  'PatientWaitingPage',
)
const AdminLoginPage = loadNamed(() => import('../pages/AdminLoginPage'), 'AdminLoginPage')
const AdminDashboardPage = loadNamed(
  () => import('../pages/AdminDashboardPage'),
  'AdminDashboardPage',
)
const NotFoundPage = loadNamed(() => import('../pages/NotFoundPage'), 'NotFoundPage')

function RouteFallback() {
  return (
    <div className="route-fallback" role="status" aria-live="polite">
      <span className="route-fallback__mark">
        <i />
        <i />
        <i />
      </span>
      <p>正在安全加载页面…</p>
    </div>
  )
}

export function App() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/doctor/login" element={<DoctorLoginPage />} />
        <Route path="/doctor/apply" element={<DoctorApplicationPage />} />
        <Route path="/doctor/workspace" element={<DoctorWorkspacePage />} />
        <Route path="/doctor/cases/:caseId" element={<DoctorCasePage />} />
        <Route
          path="/doctor/cases/:caseId/interview/:sessionId"
          element={<DoctorInterviewPage />}
        />
        <Route path="/patient/invite" element={<PatientInvitePage />} />
        <Route path="/patient/session/:sessionId" element={<PatientWaitingPage />} />
        <Route path="/admin/login" element={<AdminLoginPage />} />
        <Route path="/admin/dashboard" element={<AdminDashboardPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  )
}
