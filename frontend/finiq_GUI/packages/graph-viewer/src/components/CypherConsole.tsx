import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, Button } from '@finiq/ui'
import { Send } from 'lucide-react'
import { apiClient } from '../utils/apiClient'
import type { GraphData } from '../types/graph'

interface CypherConsoleProps {
  onCypherResult: (customGraph: GraphData) => void
}

export function CypherConsole({ onCypherResult }: CypherConsoleProps) {
  const [cypherQuery, setCypherQuery] = useState('MATCH (n:Entity) RETURN n LIMIT 25')
  const [cypherError, setCypherError] = useState<string | null>(null)
  const [cypherSuccess, setCypherSuccess] = useState(false)
  const isFallback = apiClient.getMode() === 'fallback'

  const handleRunCypher = async () => {
    setCypherError(null)
    setCypherSuccess(false)
    if (isFallback) {
      setCypherError('Custom Cypher queries are only supported when connected to the backend API.')
      return
    }

    try {
      const result = await apiClient.runCustomCypher(cypherQuery)
      setCypherSuccess(true)
      onCypherResult(result)
    } catch (e: any) {
      setCypherError(e.message || 'Cypher query execution error.')
    }
  }

  return (
    <Card className="bg-card/40">
      <CardHeader className="p-4 border-b">
        <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
          <Send className="w-4 h-4 text-blue-400" /> Interactive Cypher Query Console
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 space-y-4">
        <div className="text-xs text-muted-foreground">
          Write custom Neo4j Cypher queries directly. The returned entities will overwrite/append onto the active graph rendering panel. *(Only active when Connected to live API)*
        </div>

        <div className="grid gap-2">
          <textarea
            value={cypherQuery}
            onChange={(e) => setCypherQuery(e.target.value)}
            rows={4}
            disabled={isFallback}
            className="w-full font-mono text-xs p-3 rounded-lg border bg-background/50 focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
          />
        </div>

        {cypherError && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 text-xs rounded-lg text-red-500">
            {cypherError}
          </div>
        )}

        {cypherSuccess && (
          <div className="p-2 bg-green-500/10 border border-green-500/30 text-green-500 text-xs rounded">
            Cypher query executed successfully! Render state updated.
          </div>
        )}

        <div className="flex justify-end">
          <Button
            size="sm"
            onClick={handleRunCypher}
            disabled={isFallback}
            className="text-xs font-bold flex items-center gap-1"
          >
            <Send className="w-3.5 h-3.5" /> Execute Cypher
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
