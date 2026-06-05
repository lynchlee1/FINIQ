import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, Button } from '@finiq/ui'
import { Database, RefreshCw, CheckCircle, AlertTriangle } from 'lucide-react'
import { apiClient } from '../utils/apiClient'

interface ConnectionConfigProps {
  onRefreshGraph: () => void
}

export function ConnectionConfig({ onRefreshGraph }: ConnectionConfigProps) {
  const [isSeeding, setIsSeeding] = useState(false)
  const connectionStatus = apiClient.getMode()

  const handleSeedData = async () => {
    setIsSeeding(true)
    try {
      await apiClient.seedDefaultData()
      onRefreshGraph()
      alert('Database seeded successfully!')
    } catch (e: any) {
      alert(`Seeding failed: ${e.message}`)
    } finally {
      setIsSeeding(false)
    }
  }

  return (
    <>
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-4 border rounded-xl bg-card/60">
        <div>
          <h2 className="text-lg font-bold flex items-center gap-2">
            <Database className="w-5 h-5 text-primary" />
            Database Manager (API Mode)
          </h2>
          <p className="text-xs text-muted-foreground">
            Connects to the backend FastAPI service which manages Neo4j data and local fallback safely.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {connectionStatus === 'api' ? (
            <div className="flex items-center gap-1 bg-green-500/10 text-green-500 border border-green-500/30 px-3 py-1 rounded-full text-xs font-bold shadow-sm">
              <CheckCircle className="w-3.5 h-3.5" /> API Connected
            </div>
          ) : (
            <div className="flex items-center gap-1 bg-yellow-500/10 text-yellow-500 border border-yellow-500/30 px-3 py-1 rounded-full text-xs font-bold shadow-sm">
              <AlertTriangle className="w-3.5 h-3.5 animate-pulse" /> Local Fallback Mode
            </div>
          )}
        </div>
      </div>

      <Card className="bg-card/40 flex flex-col justify-between">
        <CardHeader className="p-4 border-b">
          <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            <RefreshCw className="w-4 h-4 text-purple-400" /> Database Seeding
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 flex-1 flex flex-col justify-between gap-4">
          <div className="text-xs text-muted-foreground leading-relaxed">
            <p className="font-bold text-foreground mb-1">Populate defaults:</p>
            Will drop existing `:Entity` nodes and edges, then seed the default corporate global dataset.
          </div>
          <div className="flex justify-end pt-4">
            <Button
              variant="outline"
              size="sm"
              onClick={handleSeedData}
              disabled={isSeeding}
              className="text-xs border-purple-500 text-purple-400 hover:bg-purple-950/20 font-bold"
            >
              {isSeeding ? 'Seeding DB...' : 'Seed Corporate Database'}
            </Button>
          </div>
        </CardContent>
      </Card>
    </>
  )
}
