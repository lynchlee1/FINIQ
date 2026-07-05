export async function fetchCompanyGraphData(companyId: string) {
  const res = await fetch(`/local-api-graph/${companyId}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch graph data: ${res.status} ${res.statusText}`);
  }
  const data = await res.json();
  return data.data;
}
