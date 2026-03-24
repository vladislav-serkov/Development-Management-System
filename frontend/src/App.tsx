import { useUIStore } from "@/stores/uiStore"

function App() {
  const selectedDocumentId = useUIStore((s) => s.selectedDocumentId)
  return (
    <div className="min-h-screen bg-background">
      <h1 className="p-4 text-2xl font-bold">Extract Agent</h1>
      <p className="p-4 text-muted-foreground">
        {selectedDocumentId ? `Project ${selectedDocumentId}` : "Home"}
      </p>
    </div>
  )
}

export default App
