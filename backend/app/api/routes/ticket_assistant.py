from fastapi import APIRouter, Depends
from ...services.ticket_assistant import TicketRankingRequest, rank_tickets
from ...services.ticket_search import SearchQuery, local_only, searches

router = APIRouter(prefix='/tickets', tags=['查票与筛选'])


@router.post('/search', dependencies=[Depends(local_only)])
async def start_search(body: SearchQuery):
    return await searches.start(body)


@router.get('/search/{search_id}', dependencies=[Depends(local_only)])
async def search_status(search_id: str):
    return (await searches.get(search_id)).public()


@router.post('/search/{search_id}/browser', dependencies=[Depends(local_only)])
async def show_search_browser(search_id: str):
    return await searches.resume(search_id, show_browser=True)


@router.post('/search/{search_id}/continue', dependencies=[Depends(local_only)])
async def continue_search(search_id: str):
    return await searches.resume(search_id)


@router.delete('/search/{search_id}', dependencies=[Depends(local_only)])
async def cancel_search(search_id: str):
    await searches.cancel(search_id)
    return {'status': 'cancelled'}


@router.post('/recommend')
async def recommend(body: TicketRankingRequest):
    return await rank_tickets(body)
