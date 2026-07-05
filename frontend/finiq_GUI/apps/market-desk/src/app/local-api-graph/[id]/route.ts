import { NextResponse } from 'next/server';
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
    console.error('Failed to read parsed JSON', err);
    return NextResponse.json(
      { success: false, error: 'Failed to read graph data.' },
      { status: 500 },
    );
  }

  return NextResponse.json(
    { success: false, error: `Graph data not found for company: ${id}` },
    { status: 404 },
  );
}
