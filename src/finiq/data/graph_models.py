from typing import Dict, Any, List, Optional
from datetime import date, datetime
from pydantic import BaseModel, Field
import uuid

# ==========================================
# 1. Base Graph Components
# ==========================================
class GraphElement(BaseModel):
    """모든 그래프 요소(Node, Edge)의 최상위 클래스"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="고유 식별자")
    properties: Dict[str, Any] = Field(
        default_factory=dict, 
        description="동적 스키마를 위한 속성 저장소 (예: 파싱된 비정형 데이터)"
    )

class GraphNode(GraphElement):
    """그래프 노드(엔티티) 베이스 클래스"""
    labels: List[str] = Field(default_factory=list, description="노드의 범주/타입 라벨")

class GraphEdge(GraphElement):
    """그래프 엣지(관계) 베이스 클래스"""
    source_id: str = Field(..., description="시작 노드의 ID")
    target_id: str = Field(..., description="도착 노드의 ID")
    edge_type: str = Field(..., description="관계의 종류 (예: HELD, VOTED_FOR, ISSUED)")
    
    # 시간적 속성 (Temporal Context)
    start_date: Optional[date] = Field(default=None, description="관계의 시작일 (예: 취임일, 발행일)")
    end_date: Optional[date] = Field(default=None, description="관계의 종료일 (예: 퇴임일, 만기일)")
    is_active: Optional[bool] = Field(default=None, description="현재 유효한 관계인지 여부")
    
    # 수치적/동적 속성을 위한 명시적 필드 (properties에도 넣을 수 있지만 자주 쓰이는 것은 빼둠)
    weight: Optional[float] = Field(default=None, description="관계의 가중치 (지분율, 금액, 의결권 등)")
    
    # 출처 (Data Provenance)
    source_url: Optional[str] = Field(default=None, description="데이터의 출처 문서 URL")
    document_type: Optional[str] = Field(default=None, description="출처 문서의 종류 (예: 정기주주총회결과)")
    parsed_at: Optional[datetime] = Field(default_factory=datetime.now, description="파싱 일시")


# ==========================================
# 2. Abstract Domain Nodes
# ==========================================
class EntityNode(GraphNode):
    """물리적/법적 주체 (회사, 사람, 기관)"""
    name: str = Field(..., description="주체의 이름")

class EventNode(GraphNode):
    """특정 시점에 일어나는 사건 (주총, 유상증자결정 등)"""
    event_date: date = Field(..., description="사건 발생일")

class ObjectNode(GraphNode):
    """사물이나 개념 (의안, 주식, 사채 등)"""
    pass


# ==========================================
# 3. Concrete Nodes (주총 & 발행 파싱 데이터 특화)
# ==========================================
class Company(EntityNode):
    labels: List[str] = Field(default=["Company", "Entity"])
    corporate_number: Optional[str] = Field(default=None, description="법인등록번호")
    stock_code: Optional[str] = Field(default=None, description="상장종목코드")

class Person(EntityNode):
    labels: List[str] = Field(default=["Person", "Entity"])

class Organization(EntityNode):
    """투자조합, 펀드 등 비법인 단체나 기관투자자"""
    labels: List[str] = Field(default=["Organization", "Entity"])

class ShareholderMeeting(EventNode):
    labels: List[str] = Field(default=["ShareholderMeeting", "Event"])
    meeting_type: str = Field(..., description="회의 종류 (예: 정기, 임시)")

class Agenda(ObjectNode):
    labels: List[str] = Field(default=["Agenda", "Object"])
    title: str = Field(..., description="의안 제목")
    status: Optional[str] = Field(default=None, description="결의 상태 (예: 원안승인, 부결, 보류)")

class IssuanceEvent(EventNode):
    labels: List[str] = Field(default=["IssuanceEvent", "Event"])
    issuance_type: str = Field(..., description="발행 형태 (예: 유상증자, 무상증자, CB발행, BW발행)")

class Security(ObjectNode):
    labels: List[str] = Field(default=["Security", "Object"])
    security_type: str = Field(..., description="증권/사채의 종류 (예: 보통주, 우선주, 제1회차 전환사채)")
    amount: Optional[int] = Field(default=None, description="발행(주식/사채) 수량")

class FundUsage(ObjectNode):
    """자금조달의 목적 (발행내역 특화)"""
    labels: List[str] = Field(default=["FundUsage", "Object"])
    usage_type: str = Field(..., description="자금사용목적 (예: 운영자금, 시설자금, 타법인증권취득자금)")
    planned_amount: Optional[float] = Field(default=None, description="배정된 금액")


# ==========================================
# 4. Common Edge Type Constants
# ==========================================
class EdgeTypes:
    # Entities <-> Events
    HELD = "HELD"               # Company -> Meeting
    EXECUTED = "EXECUTED"       # Company -> IssuanceEvent
    
    # Event <-> Objects
    INCLUDES = "INCLUDES"       # Meeting -> Agenda
    ISSUED = "ISSUED"           # IssuanceEvent -> Security
    FOR_PURPOSE = "FOR_PURPOSE" # IssuanceEvent -> FundUsage
    
    # Persons/Orgs <-> Events/Objects
    ATTENDED = "ATTENDED"       # Person -> Meeting
    VOTED_FOR = "VOTED_FOR"     # Person -> Agenda (찬성)
    VOTED_AGAINST = "VOTED_AGAINST" # Person -> Agenda (반대)
    ABSTAINED = "ABSTAINED"     # Person -> Agenda (기권)
    
    # Persons/Orgs <-> Securities
    ACQUIRED = "ACQUIRED"       # Person/Org -> Security (인수/취득)
    
    # Persons/Orgs <-> Companies
    DIRECTOR_OF = "DIRECTOR_OF" # Person -> Company (사내/사외이사 등)
    AUDITOR_OF = "AUDITOR_OF"   # Person -> Company (감사)
    AUDIT_COMMITTEE_MEMBER_OF = "AUDIT_COMMITTEE_MEMBER_OF" # Person -> Company
    CANDIDATE_FOR = "CANDIDATE_FOR" # Person -> Company
    ELECTED_AS = "ELECTED_AS"   # Person -> Company
    REMOVED_FROM = "REMOVED_FROM" # Person -> Company
    RESIGNED_FROM = "RESIGNED_FROM" # Person -> Company
    OPTION_GRANTED_BY = "OPTION_GRANTED_BY" # Person -> Company
    EXTERNAL_AUDITOR_OF = "EXTERNAL_AUDITOR_OF" # Organization -> Company
    TRANSFEROR_OF = "TRANSFEROR_OF" # Person/Organization -> Company
    TRANSFEREE_OF = "TRANSFEREE_OF" # Person/Organization -> Company
    PROPOSED_ALLOTTEE_OF = "PROPOSED_ALLOTTEE_OF" # Person/Organization -> Company
    MERGER_TARGET_OF = "MERGER_TARGET_OF" # Organization -> Company
    SHAREHOLDER_OF = "SHAREHOLDER_OF" # Person/Org -> Company (주주)

    # Persons/Orgs <-> Agendas/Organizations
    SUBJECT_OF = "SUBJECT_OF"   # Person/Org -> Agenda
    PROPOSED = "PROPOSED"       # Person/Org -> Agenda
    SERVES_AT = "SERVES_AT"     # Person -> Organization/Company
    ACQUISITION_TARGET_OF = "ACQUISITION_TARGET_OF" # Organization -> Agenda
    DIVESTMENT_TARGET_OF = "DIVESTMENT_TARGET_OF" # Organization -> Agenda
    ELECTRONIC_VOTING_MANAGER_FOR = "ELECTRONIC_VOTING_MANAGER_FOR" # Organization -> Meeting
    ELECTRONIC_VOTING_SYSTEM_PROVIDER_FOR = "ELECTRONIC_VOTING_SYSTEM_PROVIDER_FOR" # Organization -> Meeting
