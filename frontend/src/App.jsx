import AttributePanel from './components/AttributePanel'
import PromptOptions from './components/PromptOptions'
import PromptResults from './components/PromptResults'

function App() {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900 px-6 py-4">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <h1 className="text-xl font-bold tracking-tight text-white">
            🎮 Sprite Prompt Generator
          </h1>
          <nav className="flex gap-4 text-sm text-gray-400">
            <span className="cursor-pointer hover:text-white">Generate</span>
            <span className="cursor-pointer hover:text-white">Presets</span>
            <span className="cursor-pointer hover:text-white">History</span>
            <span className="cursor-pointer hover:text-white">Settings</span>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="mx-auto max-w-7xl px-6 py-6">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Attribute Selection Panel */}
          <aside className="lg:col-span-1">
            <AttributePanel />
          </aside>

          {/* Prompt Options & Results */}
          <section className="flex flex-col gap-6 lg:col-span-2">
            <PromptOptions />
            <PromptResults />
          </section>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-800 px-6 py-3 text-center text-xs text-gray-600">
        ComfyUI Sprite Character Prompt Generator — MVP
      </footer>
    </div>
  )
}

export default App
