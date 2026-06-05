import { NextResponse } from 'next/server';
import { exampleGraphData } from '@/app/company/[id]/exampleGraphData';
import fs from 'fs';
import path from 'path';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  
  try {
    // Try to read from python parser output if available
    const parsedDataPath = path.join(process.cwd(), '..', '..', 'data', 'parsed_json', `${id}_graph.json`);
    if (fs.existsSync(parsedDataPath)) {
      const fileContent = fs.readFileSync(parsedDataPath, 'utf-8');
      const jsonData = JSON.parse(fileContent);
      return NextResponse.json({ success: true, data: jsonData });
    }
  } catch (err) {
    console.error('Failed to read parsed JSON, falling back to dummy data', err);
  }

  // Simulate network delay for fallback
  await new Promise((resolve) => setTimeout(resolve, 600));

  return NextResponse.json({
    success: true,
    data: exampleGraphData,
  });
}
