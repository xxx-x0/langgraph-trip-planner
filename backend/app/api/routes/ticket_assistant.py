from fastapi import APIRouter
from ...services.ticket_assistant import TicketRankingRequest, rank_tickets

router = APIRouter(prefix='/tickets', tags=['浏览器辅助查票'])


@router.post('/recommend')
async def recommend(body: TicketRankingRequest):
    return await rank_tickets(body)
