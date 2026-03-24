import { useUIStore } from "@/stores/uiStore"
import HomePage from "@/pages/HomePage"
import ProjectPage from "@/pages/ProjectPage"

function App() {
  const selectedDocumentId = useUIStore((s) => s.selectedDocumentId)

  return (
    <div className="min-h-screen bg-background">
      {selectedDocumentId === null ? <HomePage /> : <ProjectPage />}
    </div>
  )
}

export default App
