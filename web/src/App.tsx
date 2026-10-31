import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Layout } from '@/components/app/layout'
import { OpportunitySheet } from '@/components/app/opportunity-sheet'
import { EmptyState } from '@/components/app/states'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { RowsSkeleton } from '@/components/app/states'
import { DashboardPage } from '@/pages/dashboard'
import { Compass } from 'lucide-react'
import { lazy, Suspense } from 'react'

// Dashboard loads eagerly (landing page); the rest are split so first load stays small.
const OpportunitiesPage = lazy(() => import('@/pages/opportunities').then((m) => ({ default: m.OpportunitiesPage })))
const TrackerPage = lazy(() => import('@/pages/tracker').then((m) => ({ default: m.TrackerPage })))
const DraftsPage = lazy(() => import('@/pages/drafts').then((m) => ({ default: m.DraftsPage })))
const DiscoverPage = lazy(() => import('@/pages/discover').then((m) => ({ default: m.DiscoverPage })))
const OpportunityPage = lazy(() => import('@/pages/opportunity').then((m) => ({ default: m.OpportunityPage })))
const ResearchersPage = lazy(() => import('@/pages/researchers').then((m) => ({ default: m.ResearchersPage })))
const ResearcherPage = lazy(() => import('@/pages/researcher').then((m) => ({ default: m.ResearcherPage })))
const ShortlistPage = lazy(() => import('@/pages/shortlist').then((m) => ({ default: m.ShortlistPage })))
const SettingsPage = lazy(() => import('@/pages/settings').then((m) => ({ default: m.SettingsPage })))
const ProfilePage = lazy(() => import('@/pages/profile').then((m) => ({ default: m.ProfilePage })))
const page = (el: React.ReactNode) => <Suspense fallback={<RowsSkeleton rows={6} />}>{el}</Suspense>

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: true } } })

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<><Layout /><OpportunitySheet /></>}>
              <Route index element={<DashboardPage />} />
              <Route path="opportunities" element={page(<OpportunitiesPage />)} />
              <Route path="opportunities/:id" element={page(<OpportunityPage />)} />
              <Route path="researchers" element={page(<ResearchersPage />)} />
              <Route path="researchers/:id" element={page(<ResearcherPage />)} />
              <Route path="shortlist" element={page(<ShortlistPage />)} />
              <Route path="tracker" element={page(<TrackerPage />)} />
              <Route path="drafts" element={page(<DraftsPage />)} />
              <Route path="discover" element={page(<DiscoverPage />)} />
              <Route path="settings" element={page(<SettingsPage />)} />
              <Route path="profile" element={page(<ProfilePage />)} />
              <Route path="*" element={<EmptyState icon={Compass} title="Page not found">Use the menu to get back on track.</EmptyState>} />
            </Route>
          </Routes>
        </BrowserRouter>
        <Toaster richColors position="bottom-right" />
      </TooltipProvider>
    </QueryClientProvider>
  )
}
