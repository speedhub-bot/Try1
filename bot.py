import requests

class HotmailChecker:
    def __init__(self, email):
        self.email = email

    def is_valid(self):
        # Implement validation check for Hotmail email
        return "hotmail.com" in self.email

# Example usage:
if __name__ == '__main__':
    checker = HotmailChecker('example@hotmail.com')
    if checker.is_valid():
        print(f'{checker.email} is a valid Hotmail email.')
    else:
        print(f'{checker.email} is not a valid Hotmail email.')
