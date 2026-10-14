"""Domain objects: explicit examples of abstraction, inheritance and encapsulation."""
from abc import ABC, abstractmethod


class Person(ABC):
    # Encapsulation: callers use properties instead of accessing private fields.
    def __init__(self, name):
        self.name = name

    @property
    def name(self):
        return self.__name

    @name.setter
    def name(self, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Name is required.')
        self.__name = value.strip()

    @property
    @abstractmethod
    def role(self):
        """Abstraction: every concrete person must supply a role."""


class Patient(Person):
    def __init__(self, name, gender, condition, severity):
        super().__init__(name)
        if gender not in ('female', 'male', 'other'):
            raise ValueError('Invalid gender.')
        if condition not in ('general', 'icu', 'ventilator', 'isolation'):
            raise ValueError('Invalid condition.')
        if type(severity) is not int or not 1 <= severity <= 5:
            raise ValueError('Severity must be an integer from 1 to 5.')
        self.__gender, self.__condition, self.__severity = gender, condition, severity

    @property
    def role(self):
        return 'Patient'

    @property
    def gender(self):
        return self.__gender

    @property
    def condition(self):
        return self.__condition

    @property
    def severity(self):
        return self.__severity


class Doctor(Person):
    @property
    def role(self):
        return 'Doctor'

    def can_shift(self, patient):
        # Demo rule only: an actual transfer requires a clinician's assessment.
        return patient.condition == 'general' and patient.severity <= 2


class Nurse(Person):
    @property
    def role(self):
        return 'Nurse'

    def can_release(self, bed, now):
        return bed.status == 'cleaning' and bed.cleaning_until <= now


class Bed(ABC):
    def __init__(self, row):
        self.__data = dict(row)

    @property
    def id(self):
        return self.__data['id']

    @property
    def status(self):
        return self.__data['status']

    @property
    def distance(self):
        return self.__data['distance']

    @property
    def cleaning_until(self):
        return self.__data['cleaning_until'] or 0

    @property
    @abstractmethod
    def cleaning_seconds(self):
        pass

    @abstractmethod
    def supports(self, patient):
        pass

    @abstractmethod
    def score(self, patient):
        pass


class GeneralBed(Bed):
    @property
    def cleaning_seconds(self):
        return 30

    def supports(self, patient):
        return patient.condition == 'general'

    def score(self, patient):
        return 0


class ICUBed(Bed):
    def __init__(self, row):
        super().__init__(row)
        self.__ventilator = bool(row['ventilator'])

    @property
    def cleaning_seconds(self):
        return 60

    def supports(self, patient):
        return patient.condition in ('general', 'icu') or (patient.condition == 'ventilator' and self.__ventilator)

    def score(self, patient):
        # Preserve scarce ventilators and ICU beds when a simpler bed works.
        return (10 if patient.condition == 'general' else 0) + (2 if self.__ventilator and patient.condition != 'ventilator' else 0)


class IsolationBed(Bed):
    @property
    def cleaning_seconds(self):
        return 90

    def supports(self, patient):
        return patient.condition == 'isolation'

    def score(self, patient):
        return 0


def bed_from_row(row):
    return {'general': GeneralBed, 'icu': ICUBed, 'isolation': IsolationBed}[row['kind']](row)


class Ward:
    def __init__(self, name, gender):
        self.__name, self.__gender = name, gender

    @property
    def name(self):
        return self.__name

    @property
    def gender(self):
        return self.__gender

    def accepts(self, patient):
        return self.gender == 'mixed' or self.gender == patient.gender


class Hospital:
    def __init__(self, name, wards):
        self.__name, self.__wards = name, tuple(wards)

    @property
    def name(self):
        return self.__name

    @property
    def wards(self):
        return self.__wards


class BedAllocator:
    def suggest(self, patient, rows, emergency=False):
        candidates = []
        for row in rows:
            bed = bed_from_row(row)
            ward = Ward(row['ward_name'], row['gender'])
            # Polymorphism: the same calls execute each bed subtype's rules.
            if bed.status == 'ready' and ward.accepts(patient) and bed.supports(patient):
                if emergency and row['kind'] != 'icu':
                    continue
                key = (bed.distance, bed.score(patient), bed.id) if emergency else (bed.score(patient), bed.distance, bed.id)
                candidates.append((key, row))
        return min(candidates, key=lambda item: item[0])[1] if candidates else None
