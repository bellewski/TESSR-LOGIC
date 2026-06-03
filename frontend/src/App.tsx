import { Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import Dashboard from './pages/Dashboard'
import BuildDetail from './pages/BuildDetail'
import Settings from './pages/Settings'
import PromptStudio from './pages/PromptStudio'
import ProjectContext from './pages/ProjectContext'
import BuildPipeline from './pages/BuildPipeline'
import Artifacts from './pages/Artifacts'
import Workshop from './pages/Workshop'
import Advanced from './pages/Advanced'
import Connectors from './pages/Connectors'
import Plugins from './pages/Plugins'
import Library from './pages/Library'
import BrandKits from './pages/BrandKits'

export default function App() {
  return (
    <div className="flex h-screen overflow-hidden bg-surface-900 text-slate-200">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <TopBar />
        <main className="flex flex-1 overflow-hidden">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/builds/:id" element={<BuildDetail />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/prompt-studio" element={<PromptStudio />} />
            <Route path="/project-context" element={<ProjectContext />} />
            <Route path="/pipeline" element={<BuildPipeline />} />
            <Route path="/artifacts" element={<Artifacts />} />
            <Route path="/workshop" element={<Workshop />} />
            <Route path="/connectors" element={<Connectors />} />
            <Route path="/plugins" element={<Plugins />} />
            <Route path="/library" element={<Library />} />
            <Route path="/brand-kits" element={<BrandKits />} />
            <Route path="/advanced" element={<Advanced />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}
