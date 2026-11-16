from aiogram.fsm.state import State, StatesGroup

class AddVideo(StatesGroup):
    cover=State(); caption=State(); teaser=State(); quality=State(); quality_file=State(); finish=State()
class DeleteVideo(StatesGroup): link=State()
class TopUp(StatesGroup): amount=State(); receipt=State()
class Settings(StatesGroup):
    card=State(); vip_price=State(); info=State(); referral=State(); admin_link=State()
    mandatory_channel=State(); special_channel=State(); info_caption=State()
class UserAdmin(StatesGroup):
    user_id=State(); add_amount=State(); subtract_amount=State(); message=State(); admin_permissions=State(); reject_reason=State()
class Broadcast(StatesGroup): content=State(); button_name=State(); button_url=State(); audience=State()
class Gift(StatesGroup): gift_type=State(); tariff=State(); amount=State(); winners=State(); confirm=State()
