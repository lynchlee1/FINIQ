export const exampleGraphData = {
  nodes: [
    // Companies
    { id: 'c1', label: 'FINIQ (대상회사)', type: 'Company', tags: ['상장'], properties: { market: 'KOSDAQ' } },
    { id: 'c2', label: '지주회사A', type: 'Company', tags: ['비상장'], properties: {} },
    { id: 'c3', label: '자회사B', type: 'Company', tags: ['비상장'], properties: {} },
    // Persons (Board & Shareholders)
    { id: 'p1', label: '김대표 (대표이사)', type: 'Person', tags: ['사내이사'], properties: {} },
    { id: 'p2', label: '이이사 (사내이사)', type: 'Person', tags: ['사내이사'], properties: {} },
    { id: 'p3', label: '박감사 (감사)', type: 'Person', tags: ['감사'], properties: {} },
    { id: 'p4', label: '최사외 (사외이사)', type: 'Person', tags: ['사외이사'], properties: {} },
    { id: 'p5', label: '정전무 (前이사)', type: 'Person', tags: ['퇴임'], properties: {} },
    // Orgs (Investors)
    { id: 'o1', label: '국민연금', type: 'Organization', tags: ['기관투자자'], properties: {} },
    { id: 'o2', label: '행동주의펀드K', type: 'Organization', tags: ['사모펀드'], properties: {} },
    { id: 'o3', label: '투자조합X', type: 'Organization', tags: ['FI'], properties: {} },
    
    // Shareholder Meeting Event
    { id: 'm1', label: '2024 정기주주총회', type: 'ShareholderMeeting', tags: ['정기'], properties: { date: '2024-03-25' } },
    // Agendas
    { id: 'a1', label: '제1호: 재무제표 승인', type: 'Agenda', tags: ['원안승인'], properties: {} },
    { id: 'a2', label: '제2호: 이사 선임(김대표)', type: 'Agenda', tags: ['원안승인'], properties: {} },
    { id: 'a3', label: '제3호: 이사 선임(행동주의 추천)', type: 'Agenda', tags: ['부결'], properties: {} },
    { id: 'a4', label: '제4호: 임원보수한도 승인', type: 'Agenda', tags: ['원안승인'], properties: {} },
    
    // Issuance Event (CB)
    { id: 'i1', label: '제1회차 CB 발행 결정', type: 'IssuanceEvent', tags: ['전환사채'], properties: { amount: 50000000000 } },
    // Security & Fund Usage
    { id: 's1', label: '제1회차 무보증 사모 전환사채', type: 'Security', tags: ['CB'], properties: { face_value: 50000000000 } },
    { id: 'u1', label: '타법인증권취득자금', type: 'FundUsage', tags: ['M&A'], properties: { amount: 30000000000 } },
    { id: 'u2', label: '운영자금', type: 'FundUsage', tags: ['운영'], properties: { amount: 20000000000 } },
    
    // Some minor shareholders for volume (>30 nodes)
    ...Array.from({ length: 15 }).map((_, i) => ({
      id: `minor_${i}`,
      label: `소액주주 ${i+1}`,
      type: 'Person',
      tags: ['소액주주'],
      properties: {}
    }))
  ],
  edges: [
    // Corporate Structure
    { id: 'e1', source: 'c2', target: 'c1', relation: 'SHAREHOLDER_OF', category: 'equity', weight: 35.5, directed: true },
    { id: 'e2', source: 'c1', target: 'c3', relation: 'SHAREHOLDER_OF', category: 'equity', weight: 100, directed: true },
    { id: 'e3', source: 'p1', target: 'c2', relation: 'SHAREHOLDER_OF', category: 'equity', weight: 40.0, directed: true }, // 김대표가 지주회사 최대주주
    
    // Board of Directors
    { id: 'e4', source: 'p1', target: 'c1', relation: 'DIRECTOR_OF', category: 'personnel', weight: 1, directed: true, is_active: true, start_date: '2020-03-01' },
    { id: 'e5', source: 'p2', target: 'c1', relation: 'DIRECTOR_OF', category: 'personnel', weight: 1, directed: true, is_active: true },
    { id: 'e6', source: 'p3', target: 'c1', relation: 'DIRECTOR_OF', category: 'personnel', weight: 1, directed: true, is_active: true },
    { id: 'e7', source: 'p4', target: 'c1', relation: 'DIRECTOR_OF', category: 'personnel', weight: 1, directed: true, is_active: true },
    { id: 'e8', source: 'p5', target: 'c1', relation: 'DIRECTOR_OF', category: 'personnel', weight: 1, directed: true, is_active: false, end_date: '2024-03-25' }, // 퇴임
    
    // Major Investors
    { id: 'e9', source: 'o1', target: 'c1', relation: 'SHAREHOLDER_OF', category: 'equity', weight: 8.2, directed: true },
    { id: 'e10', source: 'o2', target: 'c1', relation: 'SHAREHOLDER_OF', category: 'equity', weight: 5.1, directed: true },
    
    // Meeting & Agendas
    { id: 'e11', source: 'c1', target: 'm1', relation: 'HELD', category: 'event', weight: 1, directed: true },
    { id: 'e12', source: 'm1', target: 'a1', relation: 'INCLUDES', category: 'event', weight: 1, directed: true },
    { id: 'e13', source: 'm1', target: 'a2', relation: 'INCLUDES', category: 'event', weight: 1, directed: true },
    { id: 'e14', source: 'm1', target: 'a3', relation: 'INCLUDES', category: 'event', weight: 1, directed: true },
    { id: 'e15', source: 'm1', target: 'a4', relation: 'INCLUDES', category: 'event', weight: 1, directed: true },
    
    // Voting Behavior
    { id: 'e16', source: 'o1', target: 'a4', relation: 'VOTED_AGAINST', category: 'action', weight: 8.2, directed: true }, // 국민연금 보수한도 반대
    { id: 'e17', source: 'o2', target: 'a2', relation: 'VOTED_AGAINST', category: 'action', weight: 5.1, directed: true }, // 행동주의 사내이사 반대
    { id: 'e18', source: 'o2', target: 'a3', relation: 'VOTED_FOR', category: 'action', weight: 5.1, directed: true },     // 행동주의 추천이사 찬성
    { id: 'e19', source: 'c2', target: 'a2', relation: 'VOTED_FOR', category: 'action', weight: 35.5, directed: true },    // 지주회사 찬성
    { id: 'e20', source: 'c2', target: 'a3', relation: 'VOTED_AGAINST', category: 'action', weight: 35.5, directed: true },// 지주회사 행동주의 안건 반대
    
    // Issuance
    { id: 'e21', source: 'c1', target: 'i1', relation: 'EXECUTED', category: 'event', weight: 1, directed: true },
    { id: 'e22', source: 'i1', target: 's1', relation: 'ISSUED', category: 'event', weight: 1, directed: true },
    { id: 'e23', source: 'i1', target: 'u1', relation: 'FOR_PURPOSE', category: 'event', weight: 300, directed: true }, // weight can represent scale
    { id: 'e24', source: 'i1', target: 'u2', relation: 'FOR_PURPOSE', category: 'event', weight: 200, directed: true },
    { id: 'e25', source: 'o3', target: 's1', relation: 'ACQUIRED', category: 'transaction', weight: 500, directed: true }, // 투자조합X가 CB 전량 인수
    
    // Minor shareholders to Company
    ...Array.from({ length: 15 }).map((_, i) => ({
      id: `e_minor_${i}`,
      source: `minor_${i}`,
      target: 'c1',
      relation: 'SHAREHOLDER_OF',
      category: 'equity',
      weight: 0.1 + (Math.random() * 0.5),
      directed: true
    }))
  ]
}

export async function fetchCompanyGraphData(companyId: string) {
  try {
    const res = await fetch(`/local-api-graph/${companyId}`);
    if (!res.ok) throw new Error('Failed to fetch graph data');
    const data = await res.json();
    return data.data; // exampleGraphData
  } catch (error) {
    console.error(error);
    return exampleGraphData; // Fallback
  }
}
