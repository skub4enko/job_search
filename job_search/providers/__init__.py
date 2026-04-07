__all__ = [
    "Provider",
    "WorkUAProvider",
    "RabotaUAProvider",
    "DOUProvider",
    "JoobleProvider",
    "IndeedProvider",
    "JobsUAProvider",
    "TalentUAProvider",
    "GrcUAProvider",
    "OLXUAProvider",
    "TrudNetProvider",
    "get_providers",
]

from job_search.providers.base import Provider
from job_search.providers.dou import DOUProvider
from job_search.providers.grcua import GrcUAProvider
from job_search.providers.indeed import IndeedProvider
from job_search.providers.jobsua import JobsUAProvider
from job_search.providers.jooble import JoobleProvider
from job_search.providers.olxua import OLXUAProvider
from job_search.providers.rabotaua import RabotaUAProvider
from job_search.providers.talentua import TalentUAProvider
from job_search.providers.workua import WorkUAProvider
from job_search.providers.trudnet import TrudNetProvider


def get_providers() -> dict[str, type[Provider]]:
    return {
        "workua": WorkUAProvider,
        "rabotaua": RabotaUAProvider,
        "dou": DOUProvider,
        "jooble": JoobleProvider,
        "indeed": IndeedProvider,
        "jobsua": JobsUAProvider,
        "talentua": TalentUAProvider,
        "grcua": GrcUAProvider,
        "olxua": OLXUAProvider,
        "trudnet": TrudNetProvider,
    }
