import { useEffect, useMemo, useState } from 'react'
import { signInWithPopup, signOut, type User } from 'firebase/auth'
import { auth, firebaseSetupError, googleProvider } from '../config/firebase'
import { useRunForm } from '../hooks/useRunForm'
import {
  verifyFirebaseToken,
  getTrackerStats,
  getTrackerHistory,
  getFeatures,
  getDocsSummary,
  runAsync,
  getRun,
} from '../services/api'
import type {
  DocsSummaryResponse,
  FeatureResponse,
  RunRequest,
  RunResponse,
  TrackerStatsResponse,
  TrackerHistoryResponse,
} from '../types/api'

// Sub-components
import { LoginScreen } from './LoginScreen'
import { OnboardingFlow } from './OnboardingFlow'
import { DashboardLayout } from './DashboardLayout'
import { OverviewPanel } from './OverviewPanel'
import { PipelineForm } from './PipelineConfig'
import { ExecutionOutput } from './ExecutionOutput'

type ViewTab = 'overview' | 'pipeline' | 'logs'

async function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = String(reader.result ?? '')
      const split = result.indexOf(',')
      resolve(split >= 0 ? result.slice(split + 1) : result)
    }
    reader.onerror = () => reject(new Error('Failed to read resume file.'))
    reader.readAsDataURL(file)
  })
}

export function ConsoleDashboard() {
  const [activeTab, setActiveTab] = useState<ViewTab>('overview')
  const [firebaseUser, setFirebaseUser] = useState<User | null>(null)
  const [token, setToken] = useState('')
  const [tracker, setTracker] = useState<TrackerStatsResponse | null>(null)
  const [trackerHistory, setTrackerHistory] = useState<TrackerHistoryResponse | null>(null)
  const [apiFeatures, setApiFeatures] = useState<FeatureResponse | null>(null)
  const [docsSummary, setDocsSummary] = useState<DocsSummaryResponse | null>(null)
  const [syncRun, setSyncRun] = useState<RunResponse | null>(null)
  const [activeRunId, setActiveRunId] = useState('')

  const [linkedinEmail, setLinkedinEmail] = useState('')
  const [linkedinPassword, setLinkedinPassword] = useState('')
  const [resumeFileName, setResumeFileName] = useState('')
  const [resumeFileB64, setResumeFileB64] = useState('')
  const [onboardingComplete, setOnboardingComplete] = useState(false)

  const { form, setField } = useRunForm()
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')

  const isAuthed = useMemo(() => token.length > 0, [token])
  const latestRun = syncRun
  const currentProgress = ((latestRun?.payload as Record<string, any> | undefined)?.current_progress as Record<string, any> | undefined) ?? null

  const hasRunOutput = Boolean(syncRun)

  useEffect(() => {
    if (!token || !activeRunId || syncRun?.status !== 'running') {
      return
    }

    const timer = window.setInterval(async () => {
      try {
        const res = await getRun(token, activeRunId)
        setSyncRun(res)
        if (res.status !== 'running') {
          window.clearInterval(timer)
          setActiveRunId('')
          setMessage(res.message || 'Pipeline finished.')
          await loadPrivate()
          setActiveTab('logs')
        }
      } catch (error) {
        window.clearInterval(timer)
        setMessage(`Run status polling failed: ${String(error)}`)
      }
    }, 2000)

    return () => window.clearInterval(timer)
  }, [activeRunId, syncRun?.status, token])

  useEffect(() => {
    if (!token || !onboardingComplete) {
      return
    }
    loadPrivate()
  }, [token, onboardingComplete])

  const checklist = [
    { label: 'Google session connected', done: isAuthed },
    { label: 'Resume and LinkedIn added', done: onboardingComplete },
    { label: 'Pipeline has run', done: hasRunOutput },
    { label: 'Cover letters generated', done: Boolean((latestRun?.payload as Record<string, any> | undefined)?.cover_letters?.length) },
    { label: 'At least one application succeeded', done: Boolean((latestRun?.payload as Record<string, any> | undefined)?.counts?.applications_processed) },
  ]

  function buildRunBody(): RunRequest {
    return {
      ...form,
      max_scoring_jobs: 5,
      max_approved_candidates: 3,
      max_applications: 1,
      submission_target_successes: 1,
      linkedin_email: linkedinEmail.trim(),
      linkedin_password: linkedinPassword,
      resume_file_name: resumeFileName,
      resume_file_b64: resumeFileB64,
    } as RunRequest
  }

  async function onGoogleLogin() {
    if (!auth || !googleProvider) {
      setMessage(firebaseSetupError || 'Firebase is not configured yet.')
      return
    }
    setLoading(true)
    setMessage('')
    try {
      const result = await signInWithPopup(auth, googleProvider)
      const idToken = await result.user.getIdToken()
      await verifyFirebaseToken(idToken)
      setFirebaseUser(result.user)
      setToken(idToken)
      setLinkedinEmail(result.user.email || '')
      setMessage('Google sign-in succeeded.')
    } catch (error) {
      setMessage(`Login failed: ${String(error)}`)
    } finally {
      setLoading(false)
    }
  }

  async function onResumeFileChange(file: File | null) {
    if (!file) return
    setLoading(true)
    try {
      const b64 = await fileToBase64(file)
      setResumeFileName(file.name)
      setResumeFileB64(b64)
      setMessage(`Resume loaded: ${file.name}`)
    } catch (error) {
      setMessage(String(error))
    } finally {
      setLoading(false)
    }
  }

  function completeOnboarding() {
    if (!linkedinEmail.trim() || !linkedinPassword || !resumeFileB64) {
      setMessage('Please provide all credentials and a resume.')
      return
    }
    setOnboardingComplete(true)
    setMessage('Onboarding complete. You can run the pipeline now.')
    loadPrivate()
  }

  async function onLogout() {
    setLoading(true)
    try {
      if (auth) await signOut(auth)
      setFirebaseUser(null); setToken(''); setTracker(null); setTrackerHistory(null); setApiFeatures(null); setDocsSummary(null);
      setSyncRun(null);
      setActiveRunId('');
      setLinkedinEmail(''); setLinkedinPassword(''); setResumeFileName(''); setResumeFileB64('');
      setOnboardingComplete(false); setActiveTab('overview');
      setMessage('Logged out successfully.')
    } finally {
      setLoading(false)
    }
  }

  async function loadPrivate() {
    if (!isAuthed || !onboardingComplete) return
    try {
      const [trackerData, historyData, featuresData, docsData] = await Promise.all([
        getTrackerStats(token),
        getTrackerHistory(token),
        getFeatures(token),
        getDocsSummary(token),
      ])
      setTracker(trackerData)
      setTrackerHistory(historyData)
      setApiFeatures(featuresData)
      setDocsSummary(docsData)
    } catch (e) { setMessage(`Private load failed: ${String(e)}`) }
  }

  async function onRunSync() {
    if (latestRun?.status === 'running') {
      setMessage('A pipeline run is already in progress. Please wait for it to finish.')
      return
    }
    setLoading(true); setMessage('')
    try {
      const res = await runAsync(token, buildRunBody())
      setActiveRunId(res.run_id)
      setSyncRun({ run_id: res.run_id, status: 'running', message: 'Pipeline started.', payload: {} })
      setActiveTab('overview')
      setMessage('Pipeline started. You can watch the current agent phase live.')
    } catch (e) { setMessage(`Run failed: ${String(e)}`) }
    finally { setLoading(false) }
  }

  if (!isAuthed) {
    return (
      <LoginScreen 
        onGoogleLogin={onGoogleLogin} 
        loading={loading} 
        message={message} 
        firebaseSetupError={firebaseSetupError} 
      />
    )
  }

  if (!onboardingComplete) {
    return (
      <OnboardingFlow 
        linkedinEmail={linkedinEmail} setLinkedinEmail={setLinkedinEmail}
        linkedinPassword={linkedinPassword} setLinkedinPassword={setLinkedinPassword}
        resumeFileName={resumeFileName} onResumeFileChange={onResumeFileChange}
        completeOnboarding={completeOnboarding} onLogout={onLogout}
        loading={loading} message={message}
      />
    )
  }

  return (
    <DashboardLayout
      activeTab={activeTab} setActiveTab={setActiveTab}
      firebaseUser={firebaseUser} onLogout={onLogout}
      loading={loading} message={message} checklist={checklist}
    >
      {activeTab === 'overview' && <OverviewPanel latestRun={latestRun} tracker={tracker} trackerHistory={trackerHistory} apiFeatures={apiFeatures} docsSummary={docsSummary} />}
      {activeTab === 'pipeline' && (
        <PipelineForm 
          form={form} setField={setField} loading={loading}
          onRunSync={onRunSync}
          linkedinEmail={linkedinEmail} resumeFileName={resumeFileName}
          currentProgress={currentProgress}
          runStatus={latestRun?.status}
        />
      )}
      {activeTab === 'logs' && <ExecutionOutput latestRun={latestRun} />}
      
      {loading && (
        <div className="glass" style={{
          position: 'fixed',
          bottom: '2rem',
          right: '2rem',
          padding: '1rem 2rem',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-lg)',
          zIndex: 1000,
          display: 'flex',
          alignItems: 'center',
          gap: '1rem'
        }}>
          <div className="mono small" style={{
            width: '12px',
            height: '12px',
            borderRadius: '50%',
            background: 'var(--color-slate)',
            animation: 'pulse 1.5s infinite'
          }}></div>
          <p className="strong small">Backend is currently processing your request...</p>
        </div>
      )}
    </DashboardLayout>
  )
}
