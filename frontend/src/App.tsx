import { useUIStore } from "@/stores/uiStore"
import HomePage from "@/pages/HomePage"
import ProjectPage from "@/pages/ProjectPage"
import RulesPage from "@/pages/RulesPage"

function App() {
  const currentView = useUIStore((s) => s.currentView)

  return (
    <div className="min-h-screen bg-background">
      {currentView === "rules" ? <RulesPage /> :
       currentView === "project" ? <ProjectPage /> :
       <HomePage />}
    </div>
  )
}

export default App
