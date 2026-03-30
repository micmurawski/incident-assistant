from ace.playbook_core import Playbook


if __name__ == "__main__":
    playbook = Playbook.load_last_revision_of("test2")
    print(playbook.to_dict())